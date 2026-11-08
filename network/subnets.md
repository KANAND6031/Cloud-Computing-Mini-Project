# Subnet Allocation Plan (`10.20.0.0/16`)

This document outlines the Variable Length Subnet Masking (VLSM) allocation for the address block `10.20.0.0/16`, following the specification in Task 5 of the Cloud Computing Mini Project.

---

## 1. Subnet Allocation Table

Per requirements, subnets are allocated in order of host requirement from largest to smallest, starting contiguously at `10.20.0.0`, using the smallest prefix (tightest subnet) that satisfies $2^{32 - \text{prefix}} - 2 \ge \text{Hosts Needed}$.

| Subnet Name | Hosts Needed | Prefix Length | Subnet Mask | Network Address | Usable Host Range | Broadcast Address | Usable Hosts |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`app`** | 1,000 | `/22` | `255.255.252.0` | `10.20.0.0` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **`public`** | 250 | `/24` | `255.255.255.0` | `10.20.4.0` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **`data`** | 100 | `/25` | `255.255.255.128` | `10.20.5.0` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **`management`** | 20 | `/27` | `255.255.255.224` | `10.20.5.128` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

*Note: The remaining unallocated block `10.20.5.160` to `10.20.255.255` is preserved for future expansion.*

---

## 2. Detailed Workings and Derivations

### Base Network Block
- **Supernet**: `10.20.0.0/16`
- **Total Address Capacity**: $2^{32-16} = 2^{16} = 65,536$ addresses.
- **Allocation Strategy**: Largest to smallest requirement, contiguous placement starting at offset 0 (`10.20.0.0`), natural power-of-two CIDR alignment.

---

### Step 1: `app` Subnet (Largest: 1,000 hosts required)
1. **Host Bit Determination**:
   - Usable hosts formula: $N_{\text{usable}} = 2^h - 2 \ge 1,000$, where $h$ is the number of host bits.
   - For $h = 9$: $2^9 - 2 = 512 - 2 = 510 < 1,000$ (insufficient).
   - For $h = 10$: $2^{10} - 2 = 1,024 - 2 = 1,022 \ge 1,000$ (satisfies requirement).
2. **Prefix Length**:
   - $\text{Prefix} = 32 - h = 32 - 10 = \mathbf{/22}$.
   - Subnet Mask: `/22` corresponds to $11111111.11111111.11111100.00000000_2 = \mathbf{255.255.252.0}$.
3. **Address Calculations**:
   - **Network Address**: Starts at base `10.20.0.0`.
   - **Total Block Size**: $2^{10} = 1,024$ addresses ($4 \times /24$ blocks = third octet spans $0$ through $3$).
   - **First Usable Host**: `10.20.0.1`.
   - **Broadcast Address**: `10.20.3.255`.
   - **Last Usable Host**: `10.20.3.254`.
   - **Usable Host Range**: `10.20.0.1` – `10.20.3.254`.
   - **Total Usable Hosts**: $1,022$.
4. **Next Available Address**: `10.20.4.0`.

---

### Step 2: `public` Subnet (Second largest: 250 hosts required)
1. **Host Bit Determination**:
   - Formula: $N_{\text{usable}} = 2^h - 2 \ge 250$.
   - For $h = 7$: $2^7 - 2 = 128 - 2 = 126 < 250$ (insufficient).
   - For $h = 8$: $2^8 - 2 = 256 - 2 = 254 \ge 250$ (satisfies requirement).
2. **Prefix Length**:
   - $\text{Prefix} = 32 - h = 32 - 8 = \mathbf{/24}$.
   - Subnet Mask: `/24` corresponds to $11111111.11111111.11111111.00000000_2 = \mathbf{255.255.255.0}$.
3. **Address Calculations**:
   - **Network Address**: Placed immediately following `app` at `10.20.4.0`. (Properly aligned to 256-boundary).
   - **Total Block Size**: $2^8 = 256$ addresses.
   - **First Usable Host**: `10.20.4.1`.
   - **Broadcast Address**: `10.20.4.255`.
   - **Last Usable Host**: `10.20.4.254`.
   - **Usable Host Range**: `10.20.4.1` – `10.20.4.254`.
   - **Total Usable Hosts**: $254$.
4. **Next Available Address**: `10.20.5.0`.

---

### Step 3: `data` Subnet (Third largest: 100 hosts required)
1. **Host Bit Determination**:
   - Formula: $N_{\text{usable}} = 2^h - 2 \ge 100$.
   - For $h = 6$: $2^6 - 2 = 64 - 2 = 62 < 100$ (insufficient).
   - For $h = 7$: $2^7 - 2 = 128 - 2 = 126 \ge 100$ (satisfies requirement).
2. **Prefix Length**:
   - $\text{Prefix} = 32 - h = 32 - 7 = \mathbf{/25}$.
   - Subnet Mask: `/25` corresponds to $11111111.11111111.11111111.10000000_2 = \mathbf{255.255.255.128}$.
3. **Address Calculations**:
   - **Network Address**: Placed immediately following `public` at `10.20.5.0`. (Properly aligned to 128-boundary).
   - **Total Block Size**: $2^7 = 128$ addresses.
   - **First Usable Host**: `10.20.5.1`.
   - **Broadcast Address**: `10.20.5.127`.
   - **Last Usable Host**: `10.20.5.126`.
   - **Usable Host Range**: `10.20.5.1` – `10.20.5.126`.
   - **Total Usable Hosts**: $126$.
4. **Next Available Address**: `10.20.5.128`.

---

### Step 4: `management` Subnet (Fourth largest: 20 hosts required)
1. **Host Bit Determination**:
   - Formula: $N_{\text{usable}} = 2^h - 2 \ge 20$.
   - For $h = 4$: $2^4 - 2 = 16 - 2 = 14 < 20$ (insufficient).
   - For $h = 5$: $2^5 - 2 = 32 - 2 = 30 \ge 20$ (satisfies requirement).
2. **Prefix Length**:
   - $\text{Prefix} = 32 - h = 32 - 5 = \mathbf{/27}$.
   - Subnet Mask: `/27` corresponds to $11111111.11111111.11111111.11100000_2 = \mathbf{255.255.255.224}$.
3. **Address Calculations**:
   - **Network Address**: Placed immediately following `data` at `10.20.5.128`. (Properly aligned to 32-boundary).
   - **Total Block Size**: $2^5 = 32$ addresses.
   - **First Usable Host**: `10.20.5.129`.
   - **Broadcast Address**: `10.20.5.159`.
   - **Last Usable Host**: `10.20.5.158`.
   - **Usable Host Range**: `10.20.5.129` – `10.20.5.158`.
   - **Total Usable Hosts**: $30$.
4. **Next Available Address**: `10.20.5.160`.

---

## 3. Visual Layout of Subnet Allocations

```
10.20.0.0/16 Supernet (65,536 addresses)
+-------------------------------------------------------+
| Subnet 'app' (10.20.0.0/22)                           | 1,024 addresses
| Range: 10.20.0.0 - 10.20.3.255                        | (1,022 usable)
+-------------------------------------------------------+
| Subnet 'public' (10.20.4.0/24)                        | 256 addresses
| Range: 10.20.4.0 - 10.20.4.255                        | (254 usable)
+-------------------------------------------------------+
| Subnet 'data' (10.20.5.0/25)                          | 128 addresses
| Range: 10.20.5.0 - 10.20.5.127                        | (126 usable)
+-------------------------------------------------------+
| Subnet 'management' (10.20.5.128/27)                  | 32 addresses
| Range: 10.20.5.128 - 10.20.5.159                      | (30 usable)
+-------------------------------------------------------+
| Unallocated / Reserved Space                          | 64,096 addresses
| Range: 10.20.5.160 - 10.20.255.255                    |
+-------------------------------------------------------+
```
