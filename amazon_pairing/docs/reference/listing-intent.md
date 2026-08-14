---
okf: v0.1
type: Reference
title: Amazon listing 意图分类
tags: [amazon_pairing, routing, cover, foam, fba]
timestamp: 2026-08-14
---

# Listing 意图分类

配对对象是赛狐**可销售在线商品**，不是 EN 生产主线。有库存的皮壳/海绵不必都有 listing。

## 成品 ordinary

默认。标题里的材料词或配件短语不算对象类型：

- `with Removable Velvet Cover` / `removable cover` → 成品卖点
- `Foam Headboard Pillow` → 海绵是填充材料
- KS0244 等本身就是枕套/床笠类成品，标题含 cover 仍是 ordinary

## 真皮壳 cover

仅在明确“只卖皮壳”时：

- `cover only` / `just pillow cover` / `no filler`
- `pillow covers` / `cushion covers` 作为主商品
- MSKU 或 parentSku 含 `-cover-` 标记（分别检查，不要拼成一个字符串，否则末尾 `-Cover` 会被空格吃掉）

## 真海绵 foam

- `foam only` / `replacement foam`
- MSKU 或 parentSku 含 `-foam-` 标记
- 不是标题里单独出现 Foam

## 套件 combo

`2 pcs` / `2-piece` / `set of` / `bundle` 等。真套件进「特殊对象暂缓」，不配单品。

## FBA 先验

`switchFulfillmentTo=AFN`：绍兴压缩包装成品发 FBA 仓的概率高，套件次之，单独皮壳/海绵更低。弱信号（材料词）不得把 AFN listing 打成 cover/foam。强信号（cover only / foam only）仍可搁置。
