"""
Cria uma organização de demonstração completa para testar o sistema localmente.

    python manage.py seed_demo            # cria (falha se já existir)
    python manage.py seed_demo --reset    # apaga a demonstração anterior e recria

Tudo passa pela própria API (mesmas validações, atividades, canais e notificações
de um uso real). Só a gravação da reunião passada é gravada direto no banco, porque
depende de LiveKit e da IA; ela vem marcada como demonstração. Recusa rodar com
DEBUG desligado e troca o envio de e-mail pelo de memória.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import setup_test_environment
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    MeetingInsight,
    MeetingRecording,
    Organization,
    OrganizationMember,
    Status,
    Task,
    User,
)
from core.modules.meetings.services.insights import (
    SummaryBuilder,
    SummaryOutputSerializer,
)

API = "/api/v1/"
DEFAULT_PASSWORD = "Urban-Teste-2026"
ORG_NAME = "Urban Studio (demonstração)"

PEOPLE = {
    "teste": ("teste@urban.test", "Paulo Teste"),
    "marina": ("marina@urban.test", "Marina Costa"),
    "rafael": ("rafael@urban.test", "Rafael Lima"),
    "julia": ("julia@urban.test", "Júlia Santos"),
    "carlos": ("carlos@urban.test", "Carlos Mendes"),
}
ROLES = {"marina": "admin", "rafael": "member", "julia": "member", "carlos": "viewer"}

LABELS = [
    ("Frontend", "#3b82f6"),
    ("Backend", "#8b5cf6"),
    ("Design", "#ec4899"),
    ("Bug", "#ef4444"),
    ("Melhoria", "#22b26b"),
]

# (título, coluna, prioridade, prazo em dias a partir de hoje, responsável, etiquetas,
#  passos [(texto, feito)], dias atrás da conclusão)
PROJECTS = [
    {
        "name": "Lançamento do App",
        "description": "Primeira versão do aplicativo para iOS e Android.",
        "icon": "rocket_launch",
        "color": "#f99f11",
        "is_private": False,
        "favorite": True,
        "tasks": [
            (
                "Definir arquitetura do app",
                "done",
                "high",
                -20,
                "rafael",
                ["Backend"],
                [("Escolher stack", True), ("Desenhar módulos", True)],
                18,
            ),
            (
                "Tela de login e cadastro",
                "done",
                "high",
                -12,
                "teste",
                ["Frontend", "Design"],
                [("Layout", True), ("Validações", True), ("Testes", True)],
                10,
            ),
            (
                "Integração com pagamentos",
                "done",
                "medium",
                -6,
                "rafael",
                ["Backend"],
                [],
                4,
            ),
            (
                "Notificações push",
                "in_progress",
                "high",
                2,
                "teste",
                ["Backend", "Frontend"],
                [
                    ("Configurar serviço", True),
                    ("Permissão no app", False),
                    ("Teste em aparelho", False),
                ],
                None,
            ),
            (
                "Revisar fluxo de onboarding",
                "in_progress",
                "medium",
                0,
                "julia",
                ["Design"],
                [("Mapa da jornada", True), ("Protótipo", False)],
                None,
            ),
            (
                "Corrigir travamento no Android 12",
                "todo",
                "urgent",
                -2,
                "teste",
                ["Bug", "Frontend"],
                [],
                None,
            ),
            (
                "Publicar na App Store",
                "todo",
                "high",
                9,
                "marina",
                [],
                [("Ícones e capturas", False), ("Texto da loja", False)],
                None,
            ),
            (
                "Modo escuro",
                "todo",
                "low",
                20,
                "julia",
                ["Design", "Melhoria"],
                [],
                None,
            ),
            (
                "Monitoramento de erros",
                "todo",
                "medium",
                5,
                "rafael",
                ["Backend"],
                [],
                None,
            ),
        ],
    },
    {
        "name": "Site Institucional",
        "description": "Novo site com blog e página de contato.",
        "icon": "language",
        "color": "#3b82f6",
        "is_private": False,
        "favorite": True,
        "tasks": [
            (
                "Wireframes das páginas",
                "done",
                "medium",
                -25,
                "julia",
                ["Design"],
                [],
                24,
            ),
            (
                "Configurar hospedagem",
                "done",
                "medium",
                -16,
                "rafael",
                ["Backend"],
                [],
                15,
            ),
            (
                "Página inicial",
                "done",
                "high",
                -9,
                "teste",
                ["Frontend"],
                [("Hero", True), ("Seções", True)],
                8,
            ),
            (
                "Blog com categorias",
                "in_progress",
                "medium",
                4,
                "teste",
                ["Frontend", "Backend"],
                [("Listagem", True), ("Filtro", False)],
                None,
            ),
            (
                "Formulário de contato",
                "todo",
                "medium",
                6,
                "rafael",
                ["Backend"],
                [],
                None,
            ),
            ("Otimizar imagens", "todo", "low", 12, None, ["Melhoria"], [], None),
            ("Link quebrado no rodapé", "todo", "high", -1, "julia", ["Bug"], [], None),
        ],
    },
    {
        "name": "Campanha de Marketing",
        "description": "Campanha de lançamento nas redes sociais.",
        "icon": "campaign",
        "color": "#22b26b",
        "is_private": True,
        "favorite": False,
        "tasks": [
            ("Definir público-alvo", "done", "medium", -30, "marina", [], [], 29),
            (
                "Calendário de posts",
                "done",
                "medium",
                -14,
                "marina",
                [],
                [("Outubro", True), ("Novembro", True)],
                13,
            ),
            (
                "Peças para Instagram",
                "in_progress",
                "high",
                3,
                "julia",
                ["Design"],
                [("Carrossel", True), ("Stories", False), ("Reels", False)],
                None,
            ),
            ("Orçamento de anúncios", "todo", "medium", 7, "marina", [], [], None),
            ("Relatório da primeira semana", "todo", "low", 15, "carlos", [], [], None),
        ],
    },
    {
        "name": "Atendimento ao Cliente",
        "description": "Base de conhecimento e fluxo de suporte.",
        "icon": "support_agent",
        "color": "#8b5cf6",
        "is_private": True,
        "favorite": False,
        "tasks": [
            ("Mapear perguntas frequentes", "done", "medium", -10, "carlos", [], [], 9),
            (
                "Base de conhecimento",
                "in_progress",
                "medium",
                8,
                "teste",
                ["Frontend"],
                [("Estrutura", True), ("Primeiros artigos", False)],
                None,
            ),
            (
                "Tempo de resposta acima da meta",
                "todo",
                "urgent",
                -3,
                "marina",
                ["Bug"],
                [],
                None,
            ),
            (
                "Pesquisa de satisfação",
                "todo",
                "low",
                None,
                None,
                ["Melhoria"],
                [],
                None,
            ),
        ],
    },
]

# links reais de referência, sem endereços inventados
LINKS = [
    ("Documentação do Vue", "https://vuejs.org/guide/introduction.html"),
    ("Documentação do Django", "https://docs.djangoproject.com/"),
]


class Command(BaseCommand):
    help = "Creates a full demo organization (users, projects, tasks, chat, meetings)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete the previous demo first."
        )
        parser.add_argument("--password", default=DEFAULT_PASSWORD)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo só roda com DEBUG ligado (ambiente local).")
        # e-mails (convites, avisos) ficam em memória, nunca saem do computador
        try:
            setup_test_environment()
        except RuntimeError:  # já preparado (rodando dentro dos testes)
            pass

        emails = [email for email, _name in PEOPLE.values()]
        if User.objects.filter(email__in=emails).exists():
            if not options["reset"]:
                raise CommandError(
                    "A demonstração já existe. Use --reset para recriar."
                )
            self.reset(emails)

        with transaction.atomic():
            self.seed(options["password"])
        self.stdout.write(self.style.SUCCESS("Demonstração criada."))
        self.stdout.write(f"Entre com {PEOPLE['teste'][0]} / {options['password']}")
        self.stdout.write("Outras contas (mesma senha): " + ", ".join(emails[1:]))

    def reset(self, emails):
        users = User.objects.filter(email__in=emails)
        orgs = Organization.objects.filter(members__user__in=users).distinct()
        # as tarefas protegem as colunas (PROTECT), então saem antes dos projetos
        Task.objects.filter(sector__organization__in=orgs).delete()
        orgs.delete()
        users.delete()

    # --- helpers ---------------------------------------------------------------

    def api(self, who, method, path, data=None, status=(200, 201)):
        response = getattr(self.clients[who], method)(
            f"{API}{path}", data, format="json"
        )
        if response.status_code not in status:
            raise CommandError(
                f"{method.upper()} {path}: {response.status_code} {response.content[:300]!r}"
            )
        return response.json() if response.content else None

    def day(self, offset):
        return (
            None
            if offset is None
            else (self.today + timedelta(days=offset)).isoformat()
        )

    # --- seed ------------------------------------------------------------------

    def seed(self, password):
        self.today = timezone.localdate()
        now = timezone.now()
        self.users, self.clients = {}, {}
        for key, (email, name) in PEOPLE.items():
            user = User.objects.create_user(email=email, password=password, name=name)
            self.users[key] = user
            self.clients[key] = APIClient()
            self.clients[key].force_authenticate(user)
        uid = {key: str(user.id) for key, user in self.users.items()}

        org = self.api(
            "teste",
            "post",
            "organizations/",
            {
                "name": ORG_NAME,
                "team_size": "2-10",
                "description": "Organização de demonstração para testes locais.",
            },
        )
        org_id = org["id"]
        for key, role in ROLES.items():
            OrganizationMember.objects.create(
                organization_id=org_id, user=self.users[key], role=role
            )

        # quem cria o time já entra nele
        teams = {}
        for name, description, members in [
            (
                "Produto",
                "Design e descoberta",
                [("marina", "lead"), ("julia", "member")],
            ),
            ("Engenharia", "Front e back-end", [("rafael", "lead")]),
            (
                "Comercial",
                "Marketing e atendimento",
                [("carlos", "lead"), ("marina", "member")],
            ),
        ]:
            team = self.api(
                "teste",
                "post",
                f"organizations/{org_id}/teams/",
                {"name": name, "description": description},
            )
            teams[name] = team["id"]
            for key, role in members:
                self.api(
                    "teste",
                    "post",
                    f"organizations/{org_id}/teams/{team['id']}/members/",
                    {"user_id": uid[key], "role": role},
                )

        sectors = {}
        for project in PROJECTS:
            sector = self.api(
                "teste",
                "post",
                f"organizations/{org_id}/sectors/",
                {
                    key: project[key]
                    for key in ("name", "description", "icon", "color", "is_private")
                },
            )
            sectors[project["name"]] = sector["id"]
            self.fill_project(sector["id"], project, uid, now)

        team_links = [
            ("Lançamento do App", "Engenharia", "editor"),
            ("Lançamento do App", "Produto", "editor"),
            ("Site Institucional", "Engenharia", "editor"),
            ("Campanha de Marketing", "Comercial", "editor"),
            ("Campanha de Marketing", "Produto", "viewer"),
            ("Atendimento ao Cliente", "Comercial", "editor"),
        ]
        for sector_name, team_name, role in team_links:
            self.api(
                "teste",
                "post",
                f"sectors/{sectors[sector_name]}/teams/",
                {"team_id": teams[team_name], "role": role},
            )

        archived = self.api(
            "teste",
            "post",
            f"organizations/{org_id}/sectors/",
            {
                "name": "Projeto Piloto 2025",
                "description": "Projeto encerrado.",
                "icon": "inventory_2",
                "color": "#a1a1aa",
            },
        )
        self.api("teste", "put", f"sectors/{archived['id']}/archive/")

        app = sectors["Lançamento do App"]
        for title, url in LINKS:
            self.api(
                "teste", "post", f"sectors/{app}/links/", {"title": title, "url": url}
            )

        self.seed_meetings(app, sectors["Site Institucional"], uid, now)
        self.seed_chat(org_id, uid)
        self.api(
            "teste",
            "post",
            f"organizations/{org_id}/invitations/",
            {"email": "convidado@urban.test", "role": "member", "sector_ids": [app]},
        )

    def fill_project(self, sector_id, project, uid, now):
        for key, role in [
            ("marina", "manager"),
            ("rafael", "editor"),
            ("julia", "editor"),
            ("carlos", "viewer"),
        ]:
            self.api(
                "teste",
                "post",
                f"sectors/{sector_id}/members/",
                {"user_id": uid[key], "role": role},
            )
        if project["favorite"]:
            self.api("teste", "put", f"sectors/{sector_id}/favorite/")

        labels = {
            name: self.api(
                "teste",
                "post",
                f"sectors/{sector_id}/labels/",
                {"name": name, "color": color},
            )["id"]
            for name, color in LABELS
        }
        columns = {
            s.category: str(s.id) for s in Status.objects.filter(sector_id=sector_id)
        }

        for title, column, priority, due, assignee, tags, steps, done_ago in project[
            "tasks"
        ]:
            task = self.api(
                "teste",
                "post",
                f"sectors/{sector_id}/tasks/",
                {
                    "title": title,
                    "description": f"{title}. Tarefa de demonstração para testar o quadro.",
                    "priority": priority,
                    "due_date": self.day(due),
                    "assignee": uid[assignee] if assignee else None,
                    "label_ids": [labels[tag] for tag in tags],
                    "status": columns["todo"],
                },
            )
            for content, done in steps:
                self.api(
                    "teste",
                    "post",
                    f"tasks/{task['id']}/checklist/",
                    {"content": content, "is_done": done},
                )
            if column != "todo":
                self.api(
                    "teste",
                    "post",
                    f"tasks/{task['id']}/move/",
                    {"status": columns[column]},
                )
            if done_ago is not None:
                # espalha as conclusões nas últimas semanas para o gráfico do Dashboard
                # created a few days before it was completed, so durations stay real
                completed = now - timedelta(days=done_ago)
                Task.objects.filter(id=task["id"]).update(
                    created_at=completed - timedelta(days=3),
                    completed_at=completed,
                )
            if assignee and assignee != "teste" and column == "in_progress":
                self.api(
                    assignee,
                    "post",
                    f"tasks/{task['id']}/comments/",
                    {
                        "content": f"@{PEOPLE['teste'][1]} pode revisar quando puder?",
                        "mentions": [uid["teste"]],
                    },
                )
            if column == "in_progress" and assignee == "teste":
                self.api(
                    "marina",
                    "post",
                    f"tasks/{task['id']}/comments/",
                    {"content": "Como está o andamento? Precisa de ajuda?"},
                )

        parent = (
            Task.objects.filter(sector_id=sector_id, completed_at__isnull=True)
            .order_by("created_at")
            .first()
        )
        if parent:
            for title in ("Levantar requisitos", "Validar com o time"):
                self.api(
                    "teste",
                    "post",
                    f"sectors/{sector_id}/tasks/",
                    {
                        "title": title,
                        "parent": str(parent.id),
                        "assignee": uid["teste"],
                        "due_date": self.day(4),
                    },
                )

    def seed_meetings(self, app, site, uid, now):
        def create(sector, title, start, minutes, people, description=""):
            return self.api(
                "teste",
                "post",
                f"sectors/{sector}/meetings/",
                {
                    "title": title,
                    "description": description,
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(minutes=minutes)).isoformat(),
                    "participants": [uid[key] for key in people],
                },
            )

        create(
            app,
            "Daily do app",
            now + timedelta(hours=1),
            15,
            ["teste", "rafael", "julia"],
        )
        create(
            site,
            "Revisão do site com o cliente",
            now + timedelta(days=1, hours=2),
            60,
            ["teste", "marina"],
            "Apresentar a página inicial e o blog.",
        )
        create(
            app,
            "Planejamento da próxima sprint",
            now + timedelta(days=4),
            90,
            ["teste", "marina", "rafael", "julia"],
        )
        past = create(
            app,
            "Revisão da sprint (demonstração)",
            now - timedelta(days=2),
            45,
            ["teste", "marina", "rafael"],
        )

        meeting_id = past["id"]
        start = now - timedelta(days=2)
        recording = MeetingRecording.objects.create(
            meeting_id=meeting_id,
            egress_id=f"EG_demo_{meeting_id}",
            status=MeetingRecording.Status.READY,
            started_by=self.users["teste"],
            file_key="demo/sem-video.mp4",
            duration_seconds=58,
            ended_at=start + timedelta(minutes=1),
        )
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 7.0,
                "text": "Bom dia. Vamos revisar a sprint do aplicativo.",
            },
            {
                "id": 1,
                "start": 7.0,
                "end": 15.0,
                "text": "O login e os pagamentos foram entregues e testados.",
            },
            {
                "id": 2,
                "start": 15.0,
                "end": 24.0,
                "text": "O travamento no Android 12 ainda acontece ao abrir a câmera.",
            },
            {
                "id": 3,
                "start": 24.0,
                "end": 32.0,
                "text": "Decidimos priorizar essa correção antes da publicação.",
            },
            {
                "id": 4,
                "start": 32.0,
                "end": 41.0,
                "text": "Paulo, você assume a correção até sexta?",
            },
            {"id": 5, "start": 41.0, "end": 48.0, "text": "Combinado, eu cuido disso."},
            {
                "id": 6,
                "start": 48.0,
                "end": 58.0,
                "text": "Ainda falta decidir a data da publicação na loja.",
            },
        ]
        day = timezone.localtime(start).date()
        friday = day + timedelta(days=(4 - day.weekday()) % 7 or 7)
        raw = {
            "executive_summary": "A equipe revisou a sprint do aplicativo: login e pagamentos foram entregues, e a correção do travamento no Android 12 passou a ser prioridade antes da publicação.",
            "topics": [
                {"title": "Entregas da sprint", "segment_ids": [1]},
                {"title": "Travamento no Android 12", "segment_ids": [2, 3]},
            ],
            "decisions": [
                {
                    "text": "Priorizar a correção do travamento antes da publicação",
                    "segment_ids": [3],
                }
            ],
            "problems": [
                {
                    "text": "O app trava no Android 12 ao abrir a câmera",
                    "segment_ids": [2],
                }
            ],
            "next_steps": [
                {"text": "Corrigir o travamento no Android 12", "segment_ids": [4, 5]}
            ],
            "open_questions": [
                {"text": "Qual a data de publicação na loja?", "segment_ids": [6]}
            ],
            "actions": [
                {
                    "title": "Corrigir o travamento no Android 12",
                    "description": "Acontece ao abrir a câmera.",
                    "assignee": "Paulo",
                    "due_date": friday.isoformat(),
                    "segment_ids": [4, 5],
                },
                {
                    "title": "Definir a data de publicação",
                    "description": "",
                    "assignee": None,
                    "due_date": None,
                    "segment_ids": [6],
                },
            ],
        }
        output = SummaryOutputSerializer(data=raw)
        output.is_valid(raise_exception=True)
        people = [self.users[key] for key in ("teste", "marina", "rafael")]
        MeetingInsight.objects.create(
            recording=recording,
            status=MeetingInsight.Status.DONE,
            source_key=recording.file_key,
            language="pt",
            audio_seconds=58,
            segments=segments,
            summary=SummaryBuilder(segments, people, day).build(output.validated_data),
            transcribe_model="(demonstração)",
            summary_model="(demonstração)",
            finished_at=start + timedelta(minutes=5),
        )

    def seed_chat(self, org_id, uid):
        channels = self.api("teste", "get", f"organizations/{org_id}/chat/channels/")
        channels = channels["results"] if isinstance(channels, dict) else channels
        by_name = {channel["name"]: channel["id"] for channel in channels}
        conversation = [
            (
                "Lançamento do App",
                "rafael",
                "Subi a integração de pagamentos, já dá para testar.",
            ),
            ("Lançamento do App", "teste", "Ótimo! Vou validar ainda hoje."),
            ("Lançamento do App", "julia", "Atualizei o protótipo do onboarding."),
            (
                "Site Institucional",
                "teste",
                "A página inicial está no ar no ambiente de testes.",
            ),
            (
                "Site Institucional",
                "marina",
                "Ficou ótima. Vamos mostrar ao cliente amanhã.",
            ),
        ]
        for name, who, content in conversation:
            if name in by_name:
                self.api(
                    who,
                    "post",
                    f"chat/channels/{by_name[name]}/messages/",
                    {"content": content},
                )

        direct = self.api(
            "marina",
            "post",
            f"organizations/{org_id}/chat/direct/",
            {"user_id": uid["teste"]},
        )
        for who, content in [
            ("marina", "Oi! Consegue revisar a base de conhecimento esta semana?"),
            ("teste", "Consigo sim, olho até quinta."),
            ("marina", "Perfeito, obrigada!"),
        ]:
            self.api(
                who,
                "post",
                f"chat/channels/{direct['id']}/messages/",
                {"content": content},
            )
