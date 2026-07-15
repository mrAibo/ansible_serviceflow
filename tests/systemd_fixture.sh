#!/usr/bin/env bash
set -euo pipefail

log=/tmp/serviceflow-order.log
units=(serviceflow-alpha.service serviceflow-beta.service)

write_unit() {
    local name=$1

    sudo tee "/etc/systemd/system/serviceflow-${name}.service" >/dev/null <<EOF
[Unit]
Description=ServiceFlow ${name} integration fixture

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'printf "start-${name}\\n" >> ${log}'
ExecStop=/bin/sh -c 'printf "stop-${name}\\n" >> ${log}'
RemainAfterExit=yes
EOF
}

case "${1:-}" in
    setup)
        write_unit alpha
        write_unit beta
        sudo touch "$log"
        sudo chmod 0644 "$log"
        sudo systemctl daemon-reload
        sudo systemctl start "${units[@]}"
        sudo truncate -s 0 "$log"
        ;;
    reset)
        sudo systemctl stop "${units[@]}"
        sudo truncate -s 0 "$log"
        ;;
    cleanup)
        sudo systemctl stop "${units[@]}" 2>/dev/null || true
        sudo rm -f \
            /etc/systemd/system/serviceflow-alpha.service \
            /etc/systemd/system/serviceflow-beta.service \
            "$log"
        sudo systemctl daemon-reload
        ;;
    *)
        echo "usage: $0 {setup|reset|cleanup}" >&2
        exit 2
        ;;
esac
