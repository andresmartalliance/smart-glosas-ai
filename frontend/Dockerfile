FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_URL
ARG VITE_STANDALONE_PREVIEW=false
ARG VITE_SMART_HOST_ORIGIN
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_STANDALONE_PREVIEW=$VITE_STANDALONE_PREVIEW
ENV VITE_SMART_HOST_ORIGIN=$VITE_SMART_HOST_ORIGIN
RUN npm run build
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
