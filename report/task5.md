# Task 5: Subnetting and Network Access Control

## 1. Overview and Network Architecture

Task 5 designs and validates the network architecture for the cloud deployment. The assignment provides the base private network block `10.20.0.0/16` (65,536 total IP addresses) and requires dividing it into four functional subnets using Variable Length Subnet Masking (VLSM). 

Additionally, we implement a stateless Network Access Control List (NACL) in `network/nacl.json` to secure the `public` subnet where the reverse-proxy load balancer resides, balancing external client traffic against internal application pods while isolating data and management tiers.

```
                           +----------------------------------------+
                           |           External Clients             |
                           |   (Internet / 0.0.0.0/0 & Abusive)    |
                           +----------------------------------------+
                                     |                    |
                 Port 80/443 Traffic |                    | Blocked (198.51.100.0/24)
                                     v                    x
                 +----------------------------------------------------+
                 |           PUBLIC SUBNET (10.20.4.0/24)             |
                 |                                                    |
                 |   +--------------------------------------------+   |
                 |   |             Stateless NACL                 |   |
                 |   |   - Inbound: Deny 198.51.100.0/24          |   |
                 |   |   - Inbound: Allow 80/443 (0.0.0.0/0)      |   |
                 |   |   - Inbound: Allow SSH 22 (Management)     |   |
                 |   |   - Inbound: Allow App Replies (1024-65535)|   |
                 |   |   - Outbound: Allow 8000 to App Subnet     |   |
                 |   |   - Outbound: Allow Client Replies (Ephem) |   |
                 |   |   - Default Deny                           |   |
                 |   +--------------------------------------------+   |
                 |                         |                          |
                 |                [ Load Balancer ]                   |
                 +----------------------------------------------------+
                        |                          ^
      Outbound TCP 8000 |                          | Inbound TCP Replies
                        v                          | (Ports 1024-65535)
  +-------------------------------------+   +------------------------------------+
  |      APP SUBNET (10.20.0.0/22)      |   |   MANAGEMENT (10.20.5.128/27)      |
  |  Inference Service Pods (Port 8000) |   |   SSH Bastion / Operator Access    |
  +-------------------------------------+   +------------------------------------+
                        |
                        | (Isolated from Public Subnet)
                        v
  +-------------------------------------+
  |      DATA SUBNET (10.20.5.0/25)     |
  |  SeaweedFS S3 Storage & Databases   |
  +-------------------------------------+
```

---

## 2. Subnet Allocation and Calculations

### 2.1 Allocation Rules and Sizing

Subnetting follows the standard constraints:
1. Subnets are allocated in strict order from largest host requirement to smallest.
2. Contiguous allocation beginning at `10.20.0.0` with no unallocated gaps between adjacent subnets.
3. Minimal prefix allocation satisfying the usable host condition:
   $$\text{Usable Hosts} = 2^{32 - \text{prefix}} - 2 \ge \text{Hosts Needed}$$

### 2.2 Complete Subnet Specification Table

| Subnet Name | Hosts Needed | Prefix Length | Subnet Mask | Network Address | Usable Host Range | Broadcast Address | Usable Hosts |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`app`** | 1,000 | `/22` | `255.255.252.0` | `10.20.0.0` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **`public`** | 250 | `/24` | `255.255.255.0` | `10.20.4.0` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **`data`** | 100 | `/25` | `255.255.255.128` | `10.20.5.0` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **`management`** | 20 | `/27` | `255.255.255.224` | `10.20.5.128` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

*Unallocated Block: `10.20.5.160` through `10.20.255.255` (64,096 addresses remaining).*

### 2.3 Step-by-Step Derivations

1. **`app` Subnet (1,000 hosts needed)**:
   - $2^9 - 2 = 510 < 1,000$, whereas $2^{10} - 2 = 1,022 \ge 1,000 \implies h = 10$ host bits.
   - Prefix length: $32 - 10 = \mathbf{/22}$. Subnet mask: `255.255.252.0`.
   - Block spans 1,024 IP addresses: `10.20.0.0` to `10.20.3.255`.
   - First usable IP: `10.20.0.1`; Last usable IP: `10.20.3.254`.

2. **`public` Subnet (250 hosts needed)**:
   - Starts contiguously at `10.20.4.0`.
   - $2^7 - 2 = 126 < 250$, whereas $2^8 - 2 = 254 \ge 250 \implies h = 8$ host bits.
   - Prefix length: $32 - 8 = \mathbf{/24}$. Subnet mask: `255.255.255.0`.
   - Block spans 256 IP addresses: `10.20.4.0` to `10.20.4.255`.
   - First usable IP: `10.20.4.1`; Last usable IP: `10.20.4.254`.

3. **`data` Subnet (100 hosts needed)**:
   - Starts contiguously at `10.20.5.0`.
   - $2^6 - 2 = 62 < 100$, whereas $2^7 - 2 = 126 \ge 100 \implies h = 7$ host bits.
   - Prefix length: $32 - 7 = \mathbf{/25}$. Subnet mask: `255.255.255.128`.
   - Block spans 128 IP addresses: `10.20.5.0` to `10.20.5.127`.
   - First usable IP: `10.20.5.1`; Last usable IP: `10.20.5.126`.

4. **`management` Subnet (20 hosts needed)**:
   - Starts contiguously at `10.20.5.128`.
   - $2^4 - 2 = 14 < 20$, whereas $2^5 - 2 = 30 \ge 20 \implies h = 5$ host bits.
   - Prefix length: $32 - 5 = \mathbf{/27}$. Subnet mask: `255.255.255.224`.
   - Block spans 32 IP addresses: `10.20.5.128` to `10.20.5.159`.
   - First usable IP: `10.20.5.129`; Last usable IP: `10.20.5.158`.

---

## 3. Network Access Control List (NACL) Configuration

The NACL rules are saved in `network/nacl.json`. They guard the boundary of the `public` subnet where the load balancer runs.

### 3.1 Inbound Rules

| Rule # | Protocol | Port Range | Source CIDR | Action | Purpose |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **100** | ALL | ALL | `198.51.100.0/24` | `deny` | Immediate blacklist drop of known abusive CIDR block |
| **200** | TCP | 80 – 80 | `0.0.0.0/0` | `allow` | Allow inbound HTTP web traffic from public internet |
| **210** | TCP | 443 – 443 | `0.0.0.0/0` | `allow` | Allow inbound HTTPS web traffic from public internet |
| **220** | TCP | 22 – 22 | `10.20.5.128/27` | `allow` | Allow secure SSH administration exclusively from management subnet |
| **230** | TCP | 1024 – 65535 | `10.20.0.0/22` | `allow` | Allow inbound TCP responses from application tier back to LB ephemeral ports |
| *Default* | ALL | ALL | `0.0.0.0/0` | `deny` | Implicit default drop for unlisted traffic |

### 3.2 Outbound Rules

| Rule # | Protocol | Port Range | Destination CIDR | Action | Purpose |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **100** | TCP | 8000 – 8000 | `10.20.0.0/22` | `allow` | Forward HTTP inference requests from LB to app service pods |
| **110** | TCP | 1024 – 65535 | `0.0.0.0/0` | `allow` | Forward HTTP/HTTPS response packets back to client ephemeral ports |
| *Default* | ALL | ALL | `0.0.0.0/0` | `deny` | Implicit default drop for unlisted traffic |

---

## 4. Verification and Simulation Results

The NACL configuration was evaluated against test packets using `tools/nacl_sim.py`:

```bash
$ python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
 S01  inbound  tcp port 443   192.0.2.55      -> ALLOW (rule 210)  OK
 S02  inbound  tcp port 22    192.0.2.55      -> DENY  (no match (default deny))  OK
 S03  outbound tcp port 8000  10.20.1.1       -> ALLOW (rule 100)  OK
 S04  inbound  tcp port 443   198.51.100.9    -> DENY  (rule 100)  OK
 S05  outbound tcp port 60000 192.0.2.55      -> ALLOW (rule 110)  OK
 S06  inbound  tcp port 5432  10.20.5.20      -> DENY  (no match (default deny))  OK

Correct: 6 / 6 = 100.0%
```

### Analysis of Sample Test Cases:
1. **S01 (Inbound HTTPS from 192.0.2.55:443)**: Matches Rule 210 (`allow` port 443 from `0.0.0.0/0`).
2. **S02 (Inbound SSH from 192.0.2.55:22)**: Fails Rule 220 because `192.0.2.55` does not belong to `management` (`10.20.5.128/27`). Falls through to default `deny`.
3. **S03 (Outbound TCP 8000 to 10.20.1.1)**: `10.20.1.1` falls inside `app` subnet (`10.20.0.0/22`). Matches outbound Rule 100 (`allow`).
4. **S04 (Inbound HTTPS from 198.51.100.9:443)**: Even though port is 443, Rule 100 (`deny` on `198.51.100.0/24`) is evaluated before Rule 210 and immediately drops the packet.
5. **S05 (Outbound TCP 60000 to 192.0.2.55)**: Ephemeral return packet to client. Matches outbound Rule 110 (`allow` ephemeral ports 1024-65535).
6. **S06 (Inbound TCP 5432 from 10.20.5.20)**: Database traffic from data subnet to load balancer is unauthorized. No rule matches; rejected by default deny.

---

## 5. Technical Explanations

### 5.1 Why a Stateless NACL Needs Separate Rules for Reply Traffic

In cloud network virtualization (such as AWS VPC or Linux iptables/nftables), firewalls operate in either **stateful** or **stateless** mode:

- **Stateful Firewalls (e.g., Security Groups)** maintain an in-memory connection state table (tracking TCP sequence numbers, SYN/ACK handshake state, and IP 5-tuples). When an outbound request is permitted, the state tracking engine automatically authorizes the corresponding return packets on the reverse flow without requiring separate inbound rules.
- **Stateless NACLs (Network Access Control Lists)** inspect each individual packet strictly in isolation. A stateless filter possesses no memory of preceding packets, active TCP sessions, or connection states. It cannot determine whether an incoming packet is a new connection initiation (SYN) or an established response (ACK/DATA).

Consequently, every bidirectional communication stream requires two explicitly configured rules:
1. When external clients send requests to the load balancer on port 80/443 (inbound), the load balancer must send its HTTP responses back to the client's destination port. Because operating systems assign a dynamic, ephemeral client port (typically between 1024 and 65535) as the source of the initial request, the NACL requires an explicit **outbound rule** permitting TCP traffic to destination ports 1024–65535 (`0.0.0.0/0`).
2. Similarly, when the load balancer proxies traffic by initiating an outbound TCP connection to the backend pods in the `app` subnet on port 8000 (outbound rule 100), the backend pod replies back to the load balancer's ephemeral port. The NACL requires an explicit **inbound rule** (rule 230) allowing traffic originating from the `app` subnet (`10.20.0.0/22`) arriving on destination ports 1024–65535.

Without explicit complementary rules for response traffic in both directions, all return packets are silently discarded by the final implicit `deny` rule.

### 5.2 Why Rule Order Matters for the `198.51.100.0/24` Block

NACLs evaluate rules sequentially in ascending numerical order (from lowest rule number to highest). Processing terminates on the **first rule that matches** the packet's attributes; subsequent rules are never reached.

The abusive subnet `198.51.100.0/24` is a specific CIDR sub-block strictly contained within the universal CIDR `0.0.0.0/0` ($198.51.100.0/24 \subset 0.0.0.0/0$). 

- If the general web allowance rules were placed first (e.g., Rule 100: Allow TCP 80 `0.0.0.0/0` and Rule 110: Allow TCP 443 `0.0.0.0/0`), and the block rule placed subsequent to them (e.g., Rule 200: Deny `198.51.100.0/24`), any malicious packet from `198.51.100.9` targeting port 80 or 443 would match the broad Rule 100 or 110 first. The packet would be allowed immediately, and Rule 200 would never execute.
- By assigning the deny rule a strictly lower number (Rule 100 for `deny 198.51.100.0/24`) ahead of the broad allow rules (Rules 200 and 210 for `allow 0.0.0.0/0`), packets originating from `198.51.100.0/24` match Rule 100 first and are immediately dropped, regardless of the destination port. Only traffic from legitimate, non-blacklisted source IPs can proceed down the rule table to match the general web allow rules.
