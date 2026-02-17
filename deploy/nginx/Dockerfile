FROM nginx:alpine

# Remove default configuration
RUN rm /etc/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf /etc/nginx/conf.d/default.conf

# Create directory for certbot webroot challenges
RUN mkdir -p /var/www/certbot

# Validate configuration at build time
RUN nginx -t

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
