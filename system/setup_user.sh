sudo useradd --system --no-create-home --shell /usr/sbin/nologin img_handler
sudo mkdir -p /var/lib/img_handler/uploads
sudo chown -R img_handler:img_handler /var/lib/img_handler
sudo chmod 750 /var/lib/img_handler/uploads
