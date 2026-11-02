# ADR-004: Direct-to-Cloud Pre-Signed URLs and Ephemeral Media Storage for Asset Delivery

| Metadata | Details |
| :--- | :--- |
| **ADR ID** | ADR-004 |
| **Status** | Accepted |
| **Date** | 2025-10-24 |
| **Author** | Cloud Storage & Security Lead |
| **Deciders** | Lead Architect, Frontend Lead, Compliance Officer |

---

## Context
At the conclusion of each photobooth session, the kiosk renders high-resolution composite photo strips (1200x1800 dpi, ~8–12 MB per image) and behind-the-scenes timelapse MP4 video clips (~15–30 MB).
Customers scan an on-screen QR code using their personal smartphones to download their digital assets.

This introduces two critical challenges:
1. **Network & Backend Throughput Bottlenecks:**
   - If kiosks upload multi-megabyte media files through the FastAPI backend, and customers subsequently stream/download them through the same backend, the API servers will experience heavy network bandwidth saturation, CPU overhead from buffer proxying, and connection starvation.
2. **Privacy Regulations (Vietnam Decree 13/2023/ND-CP):**
   - Personal photo assets must not be publicly exposed to third parties without authorization.
   - Long-term storage of consumer media creates severe regulatory liability and ongoing storage hosting expenses.

## Decision
We adopt **Direct-to-Cloud Ephemeral Storage using AWS S3 / Cloudflare R2 / MinIO with Pre-Signed URLs**:
1. **Pre-Signed Upload URL (Kiosk to Storage):**
   - The kiosk captures and compiles the photo assets locally, requests a time-limited pre-signed `PUT` URL from the backend (`GET /api/v1/orders/{id}/upload-url`), and uploads directly to the S3 bucket via HTTPS. The API server proxies zero raw image binary data.
2. **Ephemeral Pre-Signed Download URL (Customer Delivery):**
   - The kiosk generates an asset retrieval QR code encoding an ephemeral download token.
   - When scanned, the customer's browser invokes `GET /api/v1/assets/{token}/download`, which redirects (HTTP 307 Temporary Redirect) to an S3 Pre-Signed `GET` URL valid for exactly 15 minutes.
3. **Automated Ephemeral Retention (72-Hour TTL):**
   - An S3 Bucket Lifecycle Policy automatically and irreversibly permanently deletes all objects older than 72 hours (`Expiration: Days: 3`).
   - Customers are notified on the download portal to save their media immediately.

## Alternatives Considered
1. **Backend Binary Proxy Streaming:**
   - *Pros:* Complete control over access headers and file naming.
   - *Cons:* Severe API server bottleneck. Hundreds of simultaneous 30 MB photo/video downloads would saturate server network interfaces and monopolize ASGI worker processes.
2. **Public S3 Bucket with Obfuscated UUID Keys:**
   - *Pros:* Simple URL generation without API overhead.
   - *Cons:* Security through obscurity. Anyone guessing or intercepting the URL retains access indefinitely; blatant violation of Vietnam Decree 13/2023/ND-CP and consumer privacy expectations.
3. **Self-Hosted Kiosk Web Server:**
   - *Pros:* No cloud storage costs; assets served directly from local kiosk SSD over local Wi-Fi.
   - *Cons:* Kiosks are frequently behind NAT / dynamic 4G connections without public IPs; customers must connect to a local kiosk Wi-Fi hotspot, creating severe friction and preventing social sharing while on the go.

## Consequences
- **Positive:**
  - Offloads 100% of binary media transfer bandwidth and storage latency from the backend compute cluster to optimized cloud object storage CDN edge locations.
  - S3 Pre-signed URLs enforce strict cryptographic expiry without requiring customers to register accounts or expose phone numbers.
  - 72-hour lifecycle auto-purge guarantees compliance with data privacy mandates and prevents compounding cloud storage costs.
- **Negative / Trade-offs:**
  - Kiosk software must handle direct S3 upload failure retries independently.
  - Pre-signed URL expiration requires customers to request fresh links if they wait longer than the initial token validity window.
