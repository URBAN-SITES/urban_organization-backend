FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_MAPBOX_API_KEY
ARG VITE_API_KEY
ARG VITE_AUTH_DOMAIN
ARG VITE_PROJECT_ID
ARG VITE_STORAGE_BUCKET
ARG VITE_MESSAGING_SENDER_ID
ARG VITE_APP_ID
ARG VITE_MEASUREMENT_ID
ARG VITE_VAPID_KEY
RUN VITE_API_BASE_URL=https://4000.michalski.app/api/v1 npm run build
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
