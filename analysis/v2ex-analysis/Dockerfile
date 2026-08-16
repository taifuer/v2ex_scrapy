FROM nginx:alpine

# Keep the large analytics payload in a separate layer so UI-only builds can reuse it.
COPY dist/*.json /usr/share/nginx/html/
RUN find /usr/share/nginx/html -maxdepth 1 -type f -name '*.json' \
      -exec sh -c 'for file do gzip -6 -c "$file" > "$file.gz"; done' sh {} +

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/assets /usr/share/nginx/html/assets
COPY dist/index.html dist/favicon.svg dist/social-preview.png /usr/share/nginx/html/

# Avoid compressing chart bundles and vector assets on the first request.
RUN find /usr/share/nginx/html/assets -type f \
      \( -name '*.js' -o -name '*.css' -o -name '*.svg' \) \
      -exec sh -c 'for file do gzip -6 -c "$file" > "$file.gz"; done' sh {} + \
    && find /usr/share/nginx/html -maxdepth 1 -type f -name '*.svg' \
      -exec sh -c 'for file do gzip -6 -c "$file" > "$file.gz"; done' sh {} +

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
