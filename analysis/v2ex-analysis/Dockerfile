FROM nginx:alpine

# Keep the large analytics payload in a separate layer so UI-only builds can reuse it.
COPY dist/*.json /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/assets /usr/share/nginx/html/assets
COPY dist/index.html dist/favicon.svg dist/social-preview.png /usr/share/nginx/html/

EXPOSE 80
