---
okf: v0.1
type: Reference
title: 回复 Tracy 的邮件草稿（Camping World）
tags: [campingworld, email, reply, draft]
timestamp: 2026-11-20
---

# 回复 Tracy 草稿

> **发送前必须人工确认**：签约主体、是否授权由 Key 直接回复、是否需要抄送 Sheng HY。
> **当前状态：暂不发送（用户 2026-11-20 指示）**。等主体与关键问题内部对齐后再发。

**To**: tracy@inventivesleep.com
**Cc**: waiter.shenghy@gmail.com（可选）
**Subject**: Re: Camping World

---

Hi Tracy,

Thank you for forwarding Kara's package. We have read the vendor documents, the CWI Vendor
Compliance Guide and the EDI Overview, and here is where we stand.

**What we can take the lead on**

1. **EDI.** We already run SPS Commerce for Pottery Barn (Williams Sonoma), and our SPS
   environment is live. Please ask SPS to add Camping World as a trading partner on our
   account (ICenTrade / C113191). We need to know:
   - the 850 / 855 / 860 / 856 / 810 / 846 specifications for CW;
   - whether adding CW changes our monthly SPS fee;
   - **whether SPS Fulfillment can generate the FedEx labels and bill them 3rd-party to
     CW's FedEx account.** We would strongly prefer to keep label generation inside SPS,
     as we do today for PB; we would only set up a separate FedEx workflow if SPS cannot
     support it.

2. **Forms.** We can complete the Vendor Information Form, the ACH Authorization and the
   Item Set-Up Sheet, and provide W-9 and COI once the contracting entity is confirmed.
   We will skip the New Store Contribution Agreement, as advised for dropship.

3. **Insurance.** Our broker will issue a COI for Category 1 products with
   $1,000,000 product liability, naming CWGS Group, LLC, Camping World, LLC and their
   parent, subsidiary and affiliate companies as additional insureds, with insurers rated
   A.M. Best A- Class VII or better. Please confirm this wording is acceptable.

4. **Item set-up.** We can supply product descriptions, unit cost, MSRP, packed weight and
   package dimensions for the Skyroom assortment. We need from CW or you:
   - the CW vendor number;
   - guidance on UPC/GS1 (can we use our existing UPCs, or must new ones be registered?);
   - expected level of HTS classification and any required Prop 65 warning selection.

**Contracting entity**

For Pottery Barn, the contract is with Centrade Inc (New Jersey), while today all shipments
leave from our U.S. Central fulfillment via Daneey LLC (USTX). We are confirming internally
whether to contract with Centrade Inc or Daneey LLC, and will revert within **3 business
days**. Please let us know if CW requires the vendor name and the ship-from entity to be the
same legal entity, or whether a third-party fulfillment warehouse is acceptable if it is
covered by our insurance.

**A few questions for you**

- What retail price band does CW expect for the Skyroom assortment (headboard wedge, gap
  filler, couch cushions)? This drives our cost and MSRP work.
- Is there a co-op / promotion calendar we should plan around?
- For dropship to residential addresses, which FedEx account should we use: #278463419 or
  #908562305?
- Is there a dropship-specific routing guide or addendum beyond the general compliance guide?

**Next steps**

Within 3 business days we will send the confirmed contracting entity and the list of
documents we can complete. We will then start SPS onboarding immediately, since the EDI
certification is the critical path (3 days to 6 weeks).

Best regards,
Key

---

## 中文备注（不发送）

- 这封信把"能做的"和"要对方给的"分开了，避免承诺未确认的主体与标签方案。
- 不要写"我们一定能用 SPS 出标签"；写成待确认，保留 FedEx 后台兜底。
- 主体部分只给时间表，不倒逼对方；同时把"第三方仓是否可接受"变成 CW 的问题。
- 零售价带问题必须问，否则 Item Setup 的成本/MSRP 没有依据。
