# FBA发货单详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/detailByShipSn.json:
    post:
      summary: FBA发货单详情
      deprecated: false
      description: ''
      operationId: detailByShipSnUsingPOST
      tags:
        - FBA/发货单
        - FBA
      parameters:
        - name: access_token
          in: query
          description: 通过获取token接口获得的token，详见 [获取 Access Token](doc-1589130)
          required: true
          example: '{{access_token}}'
          schema:
            type: string
        - name: client_id
          in: query
          description: client_id, 获取方式详见 [申请API权限](1748360)
          required: true
          example: '{{client_id}}'
          schema:
            type: string
        - name: timestamp
          in: query
          description: 13位毫秒时间戳，与当前时间差异不超过正负15分钟，示例：1668153260508
          required: true
          example: '121212'
          schema:
            type: string
        - name: nonce
          in: query
          description: '随机整数值，保证每个请求唯一，示例：11251 '
          required: true
          example: '121212'
          schema:
            type: string
        - name: sign
          in: query
          description: 请求签名，详见  [生成sign（签名）](doc-1749562)
          required: true
          example: '121212121'
          schema:
            type: string
        - name: Content-Type
          in: header
          description: 固定再header位置加入Content-Type:application/json
          example: application/json
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ShippingOrderItemsOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABShippingOrderDetailOpenVo%C2%BB
          headers: {}
          x-apifox-name: OK
        '201':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Created
        '401':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Unauthorized
        '403':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Forbidden
        '404':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-apifox-folder: FBA/发货单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-188252058-run
components:
  schemas:
    ShippingOrderItemsOpenQo:
      type: object
      properties:
        shipSn:
          type: string
          description: 发货单号
      title: ShippingOrderItemsOpenQo
      x-apifox-orders:
        - shipSn
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«ShippingOrderDetailOpenVo»:
      type: object
      properties:
        requestId:
          type: string
        code:
          type: integer
          format: int32
          description: code(默认0代表成功)
        msg:
          type: string
          description: 错误信息
        data:
          $ref: '#/components/schemas/ShippingOrderDetailOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«ShippingOrderDetailOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderDetailOpenVo:
      type: object
      properties:
        shippingOrderId:
          type: string
          description: 发货单ID
        shipSn:
          type: string
          description: 发货单号
        warehouseId:
          type: string
          description: 仓库ID
        warehouseName:
          type: string
          description: 仓库名称
        headFeeType:
          type: string
          description: 费用分摊方式（0：按计费重，1：按实重，2：按体积重，3：按SKU数量，4：自定义）
        taxFeeShareType:
          type: string
          description: 税费分摊方式
        auxFeeShareType:
          type: string
          description: 辅料分摊方式
        shipType:
          type: string
          description: 物流方式（0：空运，1：海/陆运）
        status:
          type: string
          description: 发货单状态，-1：已作废，1：待配货，2：待发货，3：已发货
        expectArrivalDate:
          type: string
          description: 预计到货时间
        shipTime:
          type: string
          description: 发货时间
        realShipTime:
          type: string
          description: 实际发货时间
        cancelTime:
          type: string
          description: 作废时间
        remark:
          type: string
          description: 备注
        allotRemark:
          type: string
          description: 调拨单备注
        volumeParam:
          type: string
          description: 体积参数
        restoreStock:
          type: string
          description: 是否恢复库存，0：未恢复，1：已恢复【已发货（扣减库存）时，恢复入库】
        restoreTime:
          type: string
          description: 恢复时间
        restoreRemark:
          type: string
          description: 恢复备注
        createUid:
          type: string
          description: 创建人ID
        createUname:
          type: string
          description: 创建人名称
        createTime:
          type: string
          description: 创建时间
        updateUid:
          type: string
          description: 更新人ID
        updateUname:
          type: string
          description: 更新人名称
        updateTime:
          type: string
          description: 更新时间
        logistics:
          type: array
          description: 物流信息
          items:
            $ref: '#/components/schemas/ShippingOrderLogisticOpenVo'
        logisticsTotalSize:
          type: string
          description: 物流总数量
        items:
          type: array
          description: 明细信息
          items:
            $ref: '#/components/schemas/ShippingOrderItemOpenVo'
        mergeShippingOrderIds:
          type: array
          description: 合并的单据号
          items:
            type: string
        itemTotalSize:
          type: string
          description: 明细总数量
        fulfilmentIds:
          type: array
          description: 配送地址信息
          items:
            type: string
        logisticId:
          type: string
          description: 引用的头程物流模板id
        logisticName:
          type: string
          description: 引用的头程物流模板
        logisticProviderId:
          type: string
          description: 物流商
        logisticProviderName:
          type: string
          description: 物流商名称
        oversea:
          type: string
          description: oversea
        logisticsCost:
          type: string
          description: 物流花费
        estimateLogisticsCost:
          type: string
          description: 评估物流花费
        logisticsCurrency:
          type: string
          description: 物流币种
        toWarehouseId:
          type: string
          description: 导入仓库ID
        toWarehouseName:
          type: string
          description: 导入仓库名称
        expectShipTime:
          type: string
          description: 预计发货时间
        allotCreateId:
          type: string
          description: 调拨创建人ID
        allotCreateName:
          type: string
          description: 调拨创建人名称
        exclusiveInventory:
          type: string
          description: 使用专属库存 0否，1是
        paid:
          type: string
          description: 标记付款 0未付款，1已付款
        isSelectShelf:
          type: string
          description: 是否勾选了手动选择货架位
        isExpediting:
          type: string
          description: 是否加急 1加急
        commodityPartsList:
          type: array
          description: 商品辅料
          items: &ref_0
            $ref: '#/components/schemas/CommodityAuxListOpenVo'
        billPartsList:
          type: array
          description: 单据辅料
          items: *ref_0
        shippingOrderOverdue:
          type: string
          description: 发货单是否逾期 0未逾期 1已经逾期
        logisticStatus:
          type: string
          description: 物流追踪状态
        hasAssembleCommodity:
          type: string
          description: 是否包含加工商品
        processUserNameList:
          type: array
          description: 调拨单审批人名称
          items:
            type: string
        canApproval:
          type: string
          description: 当前人是否有审核权限
        processUserIds:
          type: string
          description: 当前审核人
        reviewer:
          type: string
          description: 审核人
        reviewTime:
          type: string
          description: 审核时间
        reviewOpinion:
          type: string
          description: 审核建议、意见
      title: ShippingOrderDetailOpenVo
      x-apifox-orders:
        - shippingOrderId
        - shipSn
        - warehouseId
        - warehouseName
        - headFeeType
        - taxFeeShareType
        - auxFeeShareType
        - shipType
        - status
        - expectArrivalDate
        - shipTime
        - realShipTime
        - cancelTime
        - remark
        - allotRemark
        - volumeParam
        - restoreStock
        - restoreTime
        - restoreRemark
        - createUid
        - createUname
        - createTime
        - updateUid
        - updateUname
        - updateTime
        - logistics
        - logisticsTotalSize
        - items
        - mergeShippingOrderIds
        - itemTotalSize
        - fulfilmentIds
        - logisticId
        - logisticName
        - logisticProviderId
        - logisticProviderName
        - oversea
        - logisticsCost
        - estimateLogisticsCost
        - logisticsCurrency
        - toWarehouseId
        - toWarehouseName
        - expectShipTime
        - allotCreateId
        - allotCreateName
        - exclusiveInventory
        - paid
        - isSelectShelf
        - isExpediting
        - commodityPartsList
        - billPartsList
        - shippingOrderOverdue
        - logisticStatus
        - hasAssembleCommodity
        - processUserNameList
        - canApproval
        - processUserIds
        - reviewer
        - reviewTime
        - reviewOpinion
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityAuxListOpenVo:
      type: object
      properties:
        auxId:
          type: string
          description: 辅料商品ID
          examples:
            - 1
        createTime:
          type: string
          format: date-time
          description: 创建时间
        auxNum:
          type: string
          description: 辅料比例
          examples:
            - 1
        updateTime:
          type: string
          format: date-time
          description: 修改时间
        commodityNum:
          type: string
          description: 主商品比例
          examples:
            - 1
        commodityId:
          type: string
          description: 主商品id
          examples:
            - 1
        auxSku:
          type: string
          description: 辅料商品sku
          examples:
            - sku
        deliveryQuantity:
          type: string
          description: 出库数量
          examples:
            - 10
        selectedShelfOut:
          type: array
          description: 辅料货架位
          items:
            type: string
      title: CommodityAuxListOpenVo
      x-apifox-orders:
        - auxId
        - createTime
        - auxNum
        - updateTime
        - commodityNum
        - commodityId
        - auxSku
        - deliveryQuantity
        - selectedShelfOut
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderItemOpenVo:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺ID
        marketplaceId:
          type: string
          description: 站点ID
        marketplace:
          type: string
          description: 站点
        amazonShipmentId:
          type: string
          description: 亚马逊FBA货件ID
        shipSn:
          type: string
          description: 发货单号
        planSn:
          type: string
          description: 发货计划编号
        auxFee:
          type: string
          description: 辅料的费用
        sellerSku:
          type: string
          description: 卖家SKU
        fnSku:
          type: string
          description: Fulfilment Network SKU
        asin:
          type: string
          description: ASIN
        commodityId:
          type: string
          description: 商品ID
        customsTax:
          type: string
          description: 报关税费
        customsTaxCurrency:
          type: string
          description: 报关税费币种
        length:
          type: string
          description: 长
        width:
          type: string
          description: 宽
        height:
          type: string
          description: 高
        lengthUnit:
          type: string
          description: 长度单位，默认cm
        weight:
          type: string
          description: 重量
        weightUnit:
          type: string
          description: 重量单位，默认g
        cartonLength:
          type: string
          description: 箱规——长
        cartonWidth:
          type: string
          description: 箱规——宽
        cartonHeight:
          type: string
          description: 箱规——高
        cartonQty:
          type: string
          description: 单箱数量
        customsUnitPrice:
          type: number
          format: double
          description: 报关单价
        quantity:
          type: string
          description: 申报量
        shipCount:
          type: string
          description: 发货数
        availableCount:
          type: string
          description: 可用量
        localInventoryVos:
          type: array
          description: 本地可用明细
          items:
            $ref: '#/components/schemas/LocalInventoryOpenVo'
        headFee:
          type: string
          description: 自定义头程费用 / 分摊头程费用
        purchaseCost:
          type: string
          description: 采购成本
        manualPurchaseCost:
          type: string
          description: 指定采购成本
        firstHeadLogistics:
          type: string
          description: 首段头程物流
        areCasesRequired:
          type: string
          description: 包装类型 0混发 1原厂
        shipmentType:
          type: string
          description: 货件类型：SP,TLT
        caseNum:
          type: string
          description: 箱数（原厂包装）
        quantityInCase:
          type: string
          description: 单箱数量（原厂包装）
        adjustStatus:
          type: string
          description: 补录状态
        diffCount:
          type: string
          description: 差异量
        shipmentStatus:
          type: string
          description: shipmentStatus
        shippingOrderRemark:
          type: string
          description: 发货单明细备注
        quantityReceived:
          type: string
          description: 到货量
        childItems:
          type: array
          description: 子商品的信息
          items:
            $ref: '#/components/schemas/FbaShippingOrderItemGroupOpenVo'
      title: ShippingOrderItemOpenVo
      x-apifox-orders:
        - shopId
        - marketplaceId
        - marketplace
        - amazonShipmentId
        - shipSn
        - planSn
        - auxFee
        - sellerSku
        - fnSku
        - asin
        - commodityId
        - customsTax
        - customsTaxCurrency
        - length
        - width
        - height
        - lengthUnit
        - weight
        - weightUnit
        - cartonLength
        - cartonWidth
        - cartonHeight
        - cartonQty
        - customsUnitPrice
        - quantity
        - shipCount
        - availableCount
        - localInventoryVos
        - headFee
        - purchaseCost
        - manualPurchaseCost
        - firstHeadLogistics
        - areCasesRequired
        - shipmentType
        - caseNum
        - quantityInCase
        - adjustStatus
        - diffCount
        - shipmentStatus
        - shippingOrderRemark
        - quantityReceived
        - childItems
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaShippingOrderItemGroupOpenVo:
      type: object
      properties:
        shippingOrderId:
          type: string
          description: 发货单ID
        shipSn:
          type: string
          description: 发货单号
        commodityId:
          type: string
          description: 商品ID
        commoditySku:
          type: string
          description: 配对商品SKU
        commodityName:
          type: string
          description: 配对商品名称（单品级别）
        commodityImage:
          type: string
          description: 配对商品主图（单品级别）
        customsUnitPrice:
          type: string
          description: 报关单价
        quantity:
          type: string
          description: 单品发货数量
        warehouseItemId:
          type: string
          description: 仓库itemId
        warehouseFnSku:
          type: string
          description: 仓库FNSKU
        availableCount:
          type: string
          description: 可用量
        purchaseCost:
          type: string
          description: 采购成本
        headFee:
          type: string
          description: 头程费用
        selectedShelfOut:
          type: array
          description: 用户选择的出库货架位
          items:
            type: string
      title: FbaShippingOrderItemGroupOpenVo
      x-apifox-orders:
        - shippingOrderId
        - shipSn
        - commodityId
        - commoditySku
        - commodityName
        - commodityImage
        - customsUnitPrice
        - quantity
        - warehouseItemId
        - warehouseFnSku
        - availableCount
        - purchaseCost
        - headFee
        - selectedShelfOut
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    LocalInventoryOpenVo:
      type: object
      properties:
        warehouseItemId:
          type: string
          description: 仓库明细ID
        warehouseId:
          type: string
          description: 仓库ID
        warehouseName:
          type: string
          description: 仓库名称
        commoditySku:
          type: string
          description: 商品SKU
        fnSku:
          type: string
          description: fnSku
        quantity:
          type: string
          description: 可用数量
        stockWait:
          type: string
          description: 待到货数
      title: LocalInventoryOpenVo
      x-apifox-orders:
        - warehouseItemId
        - warehouseId
        - warehouseName
        - commoditySku
        - fnSku
        - quantity
        - stockWait
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderLogisticOpenVo:
      type: object
      properties:
        logisticsId:
          type: string
          description: 主键ID
        rateList:
          type: array
          items:
            $ref: '#/components/schemas/FbaShippingOrderLogisticRateDto'
        logisticsNo:
          type: string
          description: 物流商单号
        trackingNo:
          type: string
          description: 物流跟踪号
        isVolumeWeight:
          type: string
          description: 是否体积重
        volumeWeight:
          type: string
          description: 体积重
        logisticsCost:
          type: string
          description: 物流费用
        logisticsCostCurrency:
          type: string
          description: 物流费用单位
        otherCost:
          type: string
          description: 其他费用
        otherCostCurrency:
          type: string
          description: 其他费用单位
        taxCost:
          type: string
          description: 税费
        taxCostCurrency:
          type: string
          description: 税费单位
        singleLogisticsCost:
          type: string
          description: 实际物流单价
        estimateLogisticsCost:
          type: string
          description: 预估物流费用
        estimateLogisticsCostCurrency:
          type: string
          description: 预估物流费用币种
        estimateOtherCost:
          type: string
          description: 预估其他费用
        estimateOtherCostCurrency:
          type: string
          description: 预估其他费用币种
        estimateTaxCost:
          type: string
          description: 预估税费
        estimateTaxCostCurrency:
          type: string
          description: 预估税费币种
        rateYearMonth:
          type: string
          description: 汇率月份
        rate:
          type: string
          description: 汇率
      title: ShippingOrderLogisticOpenVo
      x-apifox-orders:
        - logisticsId
        - rateList
        - logisticsNo
        - trackingNo
        - isVolumeWeight
        - volumeWeight
        - logisticsCost
        - logisticsCostCurrency
        - otherCost
        - otherCostCurrency
        - taxCost
        - taxCostCurrency
        - singleLogisticsCost
        - estimateLogisticsCost
        - estimateLogisticsCostCurrency
        - estimateOtherCost
        - estimateOtherCostCurrency
        - estimateTaxCost
        - estimateTaxCostCurrency
        - rateYearMonth
        - rate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaShippingOrderLogisticRateDto:
      type: object
      properties:
        currency:
          type: string
        rate:
          type: number
      title: FbaShippingOrderLogisticRateDto
      x-apifox-orders:
        - currency
        - rate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
