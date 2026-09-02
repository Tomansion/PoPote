# ---------- build ----------
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite bakes the API base in at build time, so an absolute backend URL has to be
# passed as a build arg — a runtime env var on the container comes too late and
# does nothing. Left empty (the compose case) the app calls the same-origin
# "/api" path that nginx proxies below.
#   docker build --build-arg VITE_API_URL=https://popote-back.tomansion.fr/api
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ---------- serve ----------
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
