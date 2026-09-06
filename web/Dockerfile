FROM node:22-alpine AS build

WORKDIR /build

# Dependencies first so a source-only change reuses the install layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Only substitute our own variable, so nginx's own $host, $scheme and
# friends survive templating untouched.
ENV API_UPSTREAM=api:8000     NGINX_ENVSUBST_FILTER=API_UPSTREAM
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80
