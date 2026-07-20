#!/usr/bin/env bash
set -euo pipefail

log=/tmp/serviceflow-order.log
readiness_log=/tmp/serviceflow-alpha.log
suppress_readiness=/tmp/serviceflow-suppress-alpha-ready
http_root=/tmp/serviceflow-http
units=(
    serviceflow-alpha.service
    serviceflow-beta.service
    serviceflow-http.service
)

write_unit() {
    local name=$1
    local start_command

    start_command="printf \"start-${name}\\n\" >> ${log}"
    if [[ $name == alpha ]]; then
        start_command+="; printf \"Journal ready\\n\""
        start_command+="; if [ ! -e ${suppress_readiness} ]; then printf \"Application ready\\n\" >> ${readiness_log}; fi"
    fi

    sudo tee "/etc/systemd/system/serviceflow-${name}.service" >/dev/null <<EOF
[Unit]
Description=ServiceFlow ${name} integration fixture

[Service]
Type=oneshot
ExecStart=/bin/sh -c '${start_command}'
ExecStop=/bin/sh -c 'printf "stop-${name}\\n" >> ${log}'
RemainAfterExit=yes
EOF
}

write_http_unit() {
    sudo tee /etc/systemd/system/serviceflow-http.service >/dev/null <<EOF
[Unit]
Description=ServiceFlow HTTP integration fixture
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m http.server 18080 --bind 127.0.0.1 --directory ${http_root}
Restart=no
EOF
}

case "${1:-}" in
    setup)
        write_unit alpha
        write_unit beta
        sudo mkdir -p "$http_root"
        printf 'ready\n' | sudo tee "$http_root/health" >/dev/null
        write_http_unit
        sudo touch "$log"
        sudo chmod 0644 "$log"
        printf 'Application ready\n' | sudo tee "$readiness_log" >/dev/null
        sudo chmod 0644 "$readiness_log"
        sudo rm -f "$suppress_readiness"
        sudo systemctl daemon-reload
        sudo systemctl start "${units[@]}"
        sudo truncate -s 0 "$log"
        ;;
    reset)
        sudo systemctl stop "${units[@]}"
        sudo truncate -s 0 "$log"
        sudo rm -f "$suppress_readiness"
        ;;
    suppress-readiness)
        sudo touch "$suppress_readiness"
        ;;
    cleanup)
        sudo systemctl stop "${units[@]}" 2>/dev/null || true
        sudo rm -f \
            /etc/systemd/system/serviceflow-alpha.service \
            /etc/systemd/system/serviceflow-beta.service \
            /etc/systemd/system/serviceflow-http.service \
            "$log" \
            "$readiness_log" \
            "$suppress_readiness"
        sudo rm -rf "$http_root"
        sudo systemctl daemon-reload
        ;;
    *)
        echo "usage: $0 {setup|reset|suppress-readiness|cleanup}" >&2
        exit 2
        ;;
esac
