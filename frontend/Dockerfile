FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY package.json package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm ci --fetch-retries=5 --fetch-retry-mintimeout=2000 --fetch-retry-maxtimeout=120000
COPY . .
RUN npm run build
FROM nginx:stable-alpine
RUN apk upgrade --no-cache \
    && addgroup -g 10001 app && adduser -D -u 10001 -G app app
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
USER 10001:10001
EXPOSE 5173
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
