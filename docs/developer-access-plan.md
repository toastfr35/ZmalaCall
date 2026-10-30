# Developer access implementation plan

- [x] Server: isolated tunnel-only SSH service and manually controlled exclusive session.
- [x] Terminal: authenticated settings delivery, pinned reverse tunnel and loopback-only shell listener.
- [x] Firewall: normal server SSH limited to its directly connected Ethernet subnets (IPv4/IPv6); separate public tunnel listener.
- [x] UI: enable/disable per terminal, show selected terminal and connection instructions without secrets.
- [x] Packaging: install services/helpers with narrow permissions and retain existing SSH controls.
- [x] Requirements: review server HOST/CONFIG and terminal NET/COM requirements; add direct LLT/HLT plans and traces.
- [x] Documentation: technical guides and affected user guide sources/derived artifacts.
- [x] Validation: scoped credentials, exclusive activation, tunnel revocation and subnet restrictions. Calling regressions pass; no live call is claimed.
- [x] Deployment: server and term2, including TV plugins; private data and recovery SSH preserved.
- [x] Hardware: remote shell through server, deactivation/reconnection rejection and Samsung model discovery.
- [ ] GitHub: PR/version bump, Verify checks, merge only when green.

## Verification recorded on 30 October 2026

The deployed terminal received credentials through normal HTTPS refresh and connected
through the public hostname and router forwarding. A shell through server-loopback
port 22001 returned the intended Pi hostname with the terminal service active; both
SSH host keys matched the established device identities. A competing activation was
rejected. The tunnel account could not open a server shell, a local forward or a
different remote listening port. Deactivation terminated an established terminal
shell; reactivation rejected the previous password. Runtime credentials were removed
after deactivation.

The real nftables tests passed in isolated Linux network namespaces for both IP
families: wired local sources were accepted, non-local routed sources and Wi-Fi
ingress were rejected, and the separate tunnel port remained reachable. The deployed
Samsung driver returned the TV model. A C20 snapshot succeeded, but the camera
was facing a wall socket rather than the TV. These observations do not establish physical
input switching or video-call quality. Public-hostname testing used NAT loopback;
a terminal on a separate external network has not been exercised in this run.

Local lint, requirements validation and portable LLT/HLT suites passed. Hardware and
display scenarios skipped on Windows are not counted as passed. The server Word
guide and generated installation/user PDFs were rendered and visually inspected.
