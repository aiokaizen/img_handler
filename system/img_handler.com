server {
    listen 80;
    server_name img_handler.com;

    client_max_body_size 15m;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;

    location / {
        proxy_pass http://127.0.0.1:8764;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Pass Authorization header through
        proxy_set_header Authorization $http_authorization;

        proxy_request_buffering off;
        proxy_read_timeout 60s;
    }

    # Temporary public access (signed URL) to uploaded images
    # URL format:
    #   /images/public/<filename>?md5=<sig>&expires=<unix_ts>
    location /images/public/ {
        alias /var/lib/img_handler/uploads/;

        # Validate signature and expiry (secure_link module)
        secure_link $arg_md5,$arg_expires;
        secure_link_md5 "$secure_link_expires$uri __f0x_wagvJoj1n4@x=Fa-mT#N3,£oo?^mXz7Vln87!=Ay21RY_CHANGE_ME";

        # $secure_link = ""  -> invalid signature / missing params
        # $secure_link = "0" -> expired
        if ($secure_link = "") { return 403; }
        if ($secure_link = "0") { return 410; }

        # Serve file if it exists
        try_files $request_filename =404;

        # Optional caching headers (tune to your needs)
        add_header Cache-Control "private, max-age=300";
        add_header X-Content-Type-Options nosniff always;
    }

}
