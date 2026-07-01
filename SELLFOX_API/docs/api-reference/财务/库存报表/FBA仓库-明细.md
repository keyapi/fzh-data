# FBA仓库-明细

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/finance/fbaStockDetail/pageList.json:
    post:
      summary: FBA仓库-明细
      deprecated: false
      description: ''
      operationId: detailPageListUsingPOST
      tags:
        - 财务/库存报表
        - 库存报表
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
              $ref: '#/components/schemas/FbaWarehouseDetailOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFbaWarehouseDetailOpenPage%C2%BB
          headers: {}
          x-apifox-name: ''
        '201':
          description: Created
          headers: {}
          x-apifox-name: ''
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: ''
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: ''
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: ''
      security: []
      x-order: '2147483647'
      x-apifox-folder: 财务/库存报表
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-436026010-run
components:
  schemas:
    FbaWarehouseDetailOpenQo:
      type: object
      required:
        - startMonth
        - endMonth
      properties:
        startMonth:
          type: string
          description: 开始月份
          examples:
            - 2025-08
        endMonth:
          type: string
          description: 结束月份
          examples:
            - 2025-08
        warehouseShopIdList:
          type: array
          description: 仓库Id
          items:
            type: string
        regionId:
          type: array
          description: 区域Id
          items:
            type: string
        sellable:
          type: string
          description: 状态:0-不可售,1-可售
          enum:
            - '0'
            - '1'
        labelIds:
          type: string
          description: 产品标签
        devIds:
          type: string
          description: 业务员
        searchType:
          type: string
          description: 搜索字段
          enum:
            - msku
            - asin
            - fnSku
            - commodityName
            - sku
        searchMode:
          type: string
          description: 搜索类型 exact:精准查询 blur:模糊查询
        searchContent:
          type: string
          description: 搜索内容,多个用%±%拼接
        full_cid:
          type: string
          description: 分类,多个以逗号分割
          examples:
            - 111-,111-222-
        commodityBrandId:
          type: array
          description: 商品品牌Id
          items:
            type: string
        orderBy:
          type: string
          description: 排序字段
        desc:
          type: string
          description: 排序方式是否为降序，默认是
          enum:
            - 'true'
            - 'false'
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页条数
      title: FbaWarehouseDetailOpenQo
      x-apifox-orders:
        - startMonth
        - endMonth
        - warehouseShopIdList
        - regionId
        - sellable
        - labelIds
        - devIds
        - searchType
        - searchMode
        - searchContent
        - full_cid
        - commodityBrandId
        - orderBy
        - desc
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FbaWarehouseDetailOpenPage»:
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
          $ref: '#/components/schemas/FbaWarehouseDetailOpenPage'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FbaWarehouseDetailOpenPage»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaWarehouseDetailOpenPage:
      type: object
      properties:
        pageNum:
          type: string
          description: 当前页
        rows:
          type: array
          items:
            $ref: '#/components/schemas/FbaWarehouseDetailOpenVo'
        pageSize:
          type: string
          description: 每页条数
        totalPage:
          type: string
          description: 总页数
        totalSize:
          type: string
          description: 总条数
      title: FbaWarehouseDetailOpenPage
      x-apifox-orders:
        - pageNum
        - rows
        - pageSize
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaWarehouseDetailOpenVo:
      type: object
      properties:
        reportDate:
          type: string
          description: 月份
        fnsku:
          type: string
          description: FNSKU
        asin:
          type: string
          description: ASIN
        msku:
          type: string
          description: MSKU
        commodityName:
          type: string
          description: 品名
        commoditySku:
          type: string
          description: SKU
        labelName:
          type: string
          description: 产品标签
        devName:
          type: string
          description: 业务员
        inventoryName:
          type: string
          description: 仓库名称
        categoryName:
          type: string
          description: 分类
        brandName:
          type: string
          description: 商品品牌
        sellableName:
          type: string
          description: 库存属性
        monthBegin:
          type: string
          description: 月初库存-数量
        monthBeginCost:
          type: string
          description: 月初库存-成本
        monthBeginPurchaseCost:
          type: string
          description: 月初库存-采购成本
        monthBeginHeadTripCost:
          type: string
          description: 月初库存-头程费用
        receipts:
          type: string
          description: 货件补货-数量
        receiptsCost:
          type: string
          description: 货件补货-成本
        receiptsPurchaseCost:
          type: string
          description: 货件补货-采购成本
        receiptsHeadTripCost:
          type: string
          description: 货件补货-头程费用
        customerShipment:
          type: string
          description: 订单发货-数量
        customerShipmentCost:
          type: string
          description: 订单发货-成本
        customerShipmentPurchaseCost:
          type: string
          description: 订单发货-采购成本
        customerShipmentHeadTripCost:
          type: string
          description: 订单发货-头程费用
        customerReturn:
          type: string
          description: 买家退货-数量
        customerReturnCost:
          type: string
          description: 买家退货-成本
        customerReturnPurchaseCost:
          type: string
          description: 买家退货-采购成本
        customerReturnHeadTripCost:
          type: string
          description: 买家退货-头程费用
        vendorReturn:
          type: string
          description: 库存移除-数量
        vendorReturnCost:
          type: string
          description: 库存移除-成本
        vendorReturnPurchaseCost:
          type: string
          description: 库存移除-采购成本
        vendorReturnHeadTripCost:
          type: string
          description: 库存移除-头程费用
        warehouseInOut:
          type: string
          description: 库存转移-数量
        warehouseInOutCost:
          type: string
          description: 库存转移-成本
        warehouseInOutPurchaseCost:
          type: string
          description: 库存转移-采购成本
        warehouseInOutHeadTripCost:
          type: string
          description: 库存转移-头程费用
        adjustmentFound:
          type: string
          description: 库存盘点-已找到-数量
        adjustmentFoundCost:
          type: string
          description: 库存盘点-已找到-成本
        adjustmentFoundPurchaseCost:
          type: string
          description: 库存盘点-已找到-采购成本
        adjustmentFoundHeadTripCost:
          type: string
          description: 库存盘点-已找到-头程费用
        adjustmentLost:
          type: string
          description: 库存盘点-丢失-数量
        adjustmentLostCost:
          type: string
          description: 库存盘点-丢失-成本
        adjustmentLostPurchaseCost:
          type: string
          description: 库存盘点-丢失-采购成本
        adjustmentLostHeadTripCost:
          type: string
          description: 库存盘点-丢失-头程费用
        adjustmentDamaged:
          type: string
          description: 库存盘点-已残损-数量
        adjustmentDamagedCost:
          type: string
          description: 库存盘点-已残损-成本
        adjustmentDamagedPurchaseCost:
          type: string
          description: 库存盘点-已残损-采购成本
        adjustmentDamagedHeadTripCost:
          type: string
          description: 库存盘点-已残损-头程费用
        adjustmentDisposed:
          type: string
          description: 库存盘点-已弃置-数量
        adjustmentDisposedCost:
          type: string
          description: 库存盘点-已弃置-成本
        adjustmentDisposedPurchaseCost:
          type: string
          description: 库存盘点-已弃置-采购成本
        adjustmentDisposedHeadTripCost:
          type: string
          description: 库存盘点-已弃置-头程费用
        adjustmentOther:
          type: string
          description: 库存盘点-其他-数量
        adjustmentOtherCost:
          type: string
          description: 库存盘点-其他-成本
        adjustmentOtherPurchaseCost:
          type: string
          description: 库存盘点-其他-采购成本
        adjustmentOtherHeadTripCost:
          type: string
          description: 库存盘点-其他-头程费用
        inventoryVariance:
          type: string
          description: 库存差异-数量
        inventoryVarianceCost:
          type: string
          description: 库存差异-成本
        inventoryVariancePurchaseCost:
          type: string
          description: 库存差异-采购成本
        inventoryVarianceHeadTripCost:
          type: string
          description: 库存差异-头程费用
        inventoryVarianceNew:
          type: string
          description: 差异调整-库存差异-数量
        inventoryVarianceCostNew:
          type: string
          description: 差异调整-库存差异-成本
        inventoryVariancePurchaseCostNew:
          type: string
          description: 差异调整-库存差异-采购成本
        inventoryVarianceHeadTripCostNew:
          type: string
          description: 差异调整-库存差异-头程费用
        negativeInventoryAdjustment:
          type: string
          description: 差异调整-负库存调整-数量
        negativeInventoryAdjustmentCost:
          type: string
          description: 差异调整-负库存调整-成本
        negativeInventoryAdjustmentPurchaseCost:
          type: string
          description: 差异调整-负库存调整-采购成本
        negativeInventoryAdjustmentHeadTripCost:
          type: string
          description: 差异调整-负库存调整-头程费用
        monthEnd:
          type: string
          description: 月末库存-数量
        monthEndCost:
          type: string
          description: 月末库存-成本
        monthEndPurchaseCost:
          type: string
          description: 月末库存-采购成本
        monthEndHeadTripCost:
          type: string
          description: 月末库存-头程费用
        unknown:
          type: string
          description: 未知库存
        inTransit:
          type: string
          description: 转运中库存
        inTransitNew:
          type: string
          description: 转运中库存-数量
        inTransitCost:
          type: string
          description: 转运中库存-成本
        inTransitPurchaseCost:
          type: string
          description: 转运中库存-采购成本
        inTransitHeadTripCost:
          type: string
          description: 转运中库存-头程费用
        onWay:
          type: string
          description: 月末在途-数量
        onWayCost:
          type: string
          description: 月末在途-成本
        onWayPurchaseCost:
          type: string
          description: 月末在途-采购成本
        onWayHeadTripCost:
          type: string
          description: 月末在途-头程费用
        turnoverRate:
          type: string
          description: 库存周转率
        turnoverDays:
          type: string
          description: 库存周转天数
        isr:
          type: string
          description: 存销比
      title: FbaWarehouseDetailOpenVo
      x-apifox-orders:
        - reportDate
        - fnsku
        - asin
        - msku
        - commodityName
        - commoditySku
        - labelName
        - devName
        - inventoryName
        - categoryName
        - brandName
        - sellableName
        - monthBegin
        - monthBeginCost
        - monthBeginPurchaseCost
        - monthBeginHeadTripCost
        - receipts
        - receiptsCost
        - receiptsPurchaseCost
        - receiptsHeadTripCost
        - customerShipment
        - customerShipmentCost
        - customerShipmentPurchaseCost
        - customerShipmentHeadTripCost
        - customerReturn
        - customerReturnCost
        - customerReturnPurchaseCost
        - customerReturnHeadTripCost
        - vendorReturn
        - vendorReturnCost
        - vendorReturnPurchaseCost
        - vendorReturnHeadTripCost
        - warehouseInOut
        - warehouseInOutCost
        - warehouseInOutPurchaseCost
        - warehouseInOutHeadTripCost
        - adjustmentFound
        - adjustmentFoundCost
        - adjustmentFoundPurchaseCost
        - adjustmentFoundHeadTripCost
        - adjustmentLost
        - adjustmentLostCost
        - adjustmentLostPurchaseCost
        - adjustmentLostHeadTripCost
        - adjustmentDamaged
        - adjustmentDamagedCost
        - adjustmentDamagedPurchaseCost
        - adjustmentDamagedHeadTripCost
        - adjustmentDisposed
        - adjustmentDisposedCost
        - adjustmentDisposedPurchaseCost
        - adjustmentDisposedHeadTripCost
        - adjustmentOther
        - adjustmentOtherCost
        - adjustmentOtherPurchaseCost
        - adjustmentOtherHeadTripCost
        - inventoryVariance
        - inventoryVarianceCost
        - inventoryVariancePurchaseCost
        - inventoryVarianceHeadTripCost
        - inventoryVarianceNew
        - inventoryVarianceCostNew
        - inventoryVariancePurchaseCostNew
        - inventoryVarianceHeadTripCostNew
        - negativeInventoryAdjustment
        - negativeInventoryAdjustmentCost
        - negativeInventoryAdjustmentPurchaseCost
        - negativeInventoryAdjustmentHeadTripCost
        - monthEnd
        - monthEndCost
        - monthEndPurchaseCost
        - monthEndHeadTripCost
        - unknown
        - inTransit
        - inTransitNew
        - inTransitCost
        - inTransitPurchaseCost
        - inTransitHeadTripCost
        - onWay
        - onWayCost
        - onWayPurchaseCost
        - onWayHeadTripCost
        - turnoverRate
        - turnoverDays
        - isr
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
