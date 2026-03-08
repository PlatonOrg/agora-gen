# Stage 1: Build
# Use node:22-slim. "Slim" (Debian) is more stable for Angular 20 builds than Alpine.
FROM node:22-slim AS builder

WORKDIR /app

# Copy package files first to leverage layer caching.
COPY front/package*.json ./

# Install dependencies.
RUN npm install --legacy-peer-deps

# Copy source code.
COPY front/ .

# Copy shared resources folder (components metadata, videos, etc.).
COPY resources/ ./resources/

# Build the app. Outputs to /app/dist/angular-agora/browser.
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Create a non-root user to run the Nginx worker processes.
RUN addgroup -S nginx_group && adduser -S -G nginx_group nginx_user

# Remove the default Nginx placeholder page.
RUN rm -rf /usr/share/nginx/html/*

# Angular 17+ places the static build under dist/<project-name>/browser.
COPY --from=builder /app/dist/angular-agora/browser /usr/share/nginx/html

# Angular SSR builds output index.csr.html; rename to the standard index.html.
RUN mv /usr/share/nginx/html/index.csr.html /usr/share/nginx/html/index.html || true

# Copy shared resources so they are available to the Nginx host at runtime.
COPY --from=builder /app/resources /usr/share/nginx/html/resources

# Set correct ownership of all served files for the non-root user.
RUN chown -R nginx_user:nginx_group /usr/share/nginx/html \
    && chown -R nginx_user:nginx_group /var/cache/nginx \
    && chown -R nginx_user:nginx_group /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx_user:nginx_group /var/run/nginx.pid

COPY front/nginx.conf /etc/nginx/nginx.conf

USER nginx_user

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
