FROM odoo:18.0

USER root

# Install any additional Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy custom addons
COPY ./addons /mnt/extra-addons

# Copy Odoo configuration
COPY ./odoo.conf /etc/odoo/odoo.conf

# Fix permissions
RUN chown -R odoo:odoo /mnt/extra-addons && \
    chown odoo:odoo /etc/odoo/odoo.conf

USER odoo
