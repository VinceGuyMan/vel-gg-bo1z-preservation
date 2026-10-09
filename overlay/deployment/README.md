Optional review templates only. This candidate's player-hosted Quick Tunnel mode uses Cloudflare and needs no paid server/account or custom domain; these Docker/Caddy templates are an alternative unexecuted operator deployment, requiring separate authorization and cost/domain decisions. No image/container/proxy/cloud/DNS operation has run.

Build a fresh small context containing only Dockerfile, .dockerignore, signaling.py, host_settings.py, ws_relay.py, ws_wire.py and ws-transport.js. Never include captured game assets. Keep each source identical to the package SHA256SUMS; relay ADAPTER hashes the actual ws-transport.js file at import. Current source pins:

- signaling.py: `69dfd3f0e9280e6a415774ef315dd02a19fa28ce5dce3d0fb813678ad6809de3`
- host_settings.py: `8754dd8ab964436443ce428dd4cae03e7b2bb31b0473686048996a9f85874f3c`
- ws_relay.py: `71c4647a37a6d71a04ee968958ddad21de0d563b2dbc037dc3420ce8f456810a`
- ws_wire.py: `1305e7ad0f17a4ba6a2fd34ad99806c89482b74e693ba01ef6f48032c3aab58a`
- ws-transport.js: `05cd0c02e945ba6bf42fea99db0f296beb7179e68d95667c3d645bc64cb4a7dc`

The Python image tag is a mutable template, not a verified image/digest. Docker/Podman/Caddy are unavailable here; no parser/runtime validation is claimed. The container uses a non-root user, no bytecode, invitation-required joins, SIGINT clean shutdown and health-only check. Default allowed game origins are exact localhost/127.0.0.1 port8767. Replace CMD with the entire intended allowed-origin list if needed; keep capability authentication and original Origin intact.

Caddy routes only health/API and exact /coop/ws; all other paths404. Its reverse proxy supports WebSocket upgrade by default; actual browser/proxy handshake must still be tested. No arbitrary fixture/asset/native routes, retries, cache, authentication substitution or access logging are added. JSON body limit163840 and20s polling remain. The accepted upgrade requires the exact configured Origin and protocol, then first-frame one-use ticket. No URL capability/ticket is used.

One RAM backend only: room/WS membership cannot be split across replicas. Existing room/lease/socket/rate/queue/byte limits remain; proxy collapse of source-IP create/join rate buckets remains intentional for this small experiment, and forwarded headers are not trusted. Provider can read relayed traffic after TLS termination. The new relay does not provide TURN, TCP performance guarantees, native state restoration or forced-relay proof. Explicit configured TURN is unchanged for WebRTC; no credential belongs in a static package, Dockerfile, URL or build metadata.

Actual container/HTTPS/WebSocket/browser/proxy/Windows/native and provider load remain separate unverified gates. Do not turn a health pass into gameplay admission. Keep service private HTTP behind the proxy, avoid debug credential/body logs, and use a reviewed immutable image before any authorized deployment.
