# 获取FBA发货单列表（2.0）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/pageList/v2.json:
    post:
      summary: 获取FBA发货单列表（2.0）
      deprecated: false
      description: ''
      operationId: shippingOrderPageListV2UsingPOST
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
              $ref: '#/components/schemas/ShippingOrderSearchOpenV2Qo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABShippingOrderOpenV2Vo%C2%BB%C2%BB
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
      x-apifox-folder: FBA/发货单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-484693170-run
components:
  schemas:
    ShippingOrderSearchOpenV2Qo:
      type: object
      properties:
        costUpdateFields:
          type: array
          description: >-
            费用更新时间筛选字段，可多选。可选值：estimateLogisticsCost,estimateOtherCost,estimateTaxCost,logisticsCost,otherCost,taxCost
          items:
            type: string
        pageNo:
          type: string
          description: 第几页
        costUpdateStartTime:
          type: string
          description: 费用更新时间开始时间，格式:yyyy-MM-dd HH:mm:ss
        pageSize:
          type: string
          description: 每页大小
        costUpdateEndTime:
          type: string
          description: 费用更新时间结束时间，格式:yyyy-MM-dd HH:mm:ss
        status:
          type: string
          description: 发货单状态 1待配货，2代发货，3已发货，-1已取消
        shipSns:
          type: array
          description: 发货单号
          items:
            type: string
        warehouseId:
          type: string
          description: 仓库ID
        shopIds:
          type: array
          description: 店铺, 多选，以逗号分隔
          items:
            type: string
        isExpediting:
          type: string
          description: 是否加急 true 加急  false 不加急
        relAuxFlag:
          type: integer
          format: int32
          description: 是否关联辅料:0未关联，1已关联 不传为全部
          examples:
            - 1
        createTimeStart:
          type: string
          description: 创建时间开始于，yyyy-MM-dd
          examples:
            - '2026-01-01'
        createTimeEnd:
          type: string
          description: 创建时间结束于，yyyy-MM-dd
          examples:
            - '2026-12-31'
      title: ShippingOrderSearchOpenV2Qo
      x-apifox-orders:
        - costUpdateFields
        - pageNo
        - costUpdateStartTime
        - pageSize
        - costUpdateEndTime
        - status
        - shipSns
        - warehouseId
        - shopIds
        - isExpediting
        - relAuxFlag
        - createTimeStart
        - createTimeEnd
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ShippingOrderOpenV2Vo»»:
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
          $ref: '#/components/schemas/Page%C2%ABShippingOrderOpenV2Vo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ShippingOrderOpenV2Vo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«ShippingOrderOpenV2Vo»:
      type: object
      properties:
        pageNo:
          type: integer
          format: int32
          description: 页码
        pageSize:
          type: integer
          format: int32
          description: 每页条数
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 总条数
        rows:
          type: array
          description: 当前页数据
          items:
            $ref: '#/components/schemas/ShippingOrderOpenV2Vo'
      title: Page«ShippingOrderOpenV2Vo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderOpenV2Vo:
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
        headFeeType:
          type: string
          description: 费用分摊方式（0：按计费重，1：按实重，2：按体积重，3：按SKU数量，4：自定义）
        shipType:
          type: string
          description: '运输方式（0：空运，1：海/陆运） '
        status:
          type: string
          description: 发货单状态，-1：已作废，1：待配货，2：待发货，3：已发货',
        expectArrivalDate:
          type: string
          description: 预计到货时间 yyyy-MM-dd
        shipTime:
          type: string
          description: 发货时间 yyyy-MM-dd HH:mm:ss
        realShipTime:
          type: string
          description: 实际发货时间 yyyy-MM-dd
        cancelTime:
          type: string
          description: 作废时间 yyyy-MM-dd HH:mm:ss
        remark:
          type: string
          description: 备注
        volumeParam:
          type: string
          description: 体积参数
        restoreStock:
          type: string
          description: 是否恢复库存，0：未恢复，1：已恢复【已发货（扣减库存）时，恢复入库】
        restoreTime:
          type: string
          description: 恢复库存时间 yyyy-MM-dd HH:mm:ss
        restoreRemark:
          type: string
          description: 恢复库存备注
        createUid:
          type: string
          description: 创建人ID
        createTime:
          type: string
          description: 创建时间 yyyy-MM-dd HH:mm:ss
        updateUid:
          type: string
          description: 更新人ID
        updateTime:
          type: string
          description: 更新时间 yyyy-MM-dd HH:mm:ss
        requisitionStatus:
          type: string
          description: 请款状态 ，0 未请款 ，1：部分请款，2：全部请款
        logistics:
          type: array
          description: 物流信息
          items:
            $ref: '#/components/schemas/ShippingOrderLogisticOpenV2Vo'
        logisticsTotalSize:
          type: string
          description: 物流总数量
        itemTotalSize:
          type: string
          description: 明细总数量,
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
          description: 头程物流名称
        logisticProviderId:
          type: string
          description: 物流商Id
        logisticProviderName:
          type: string
          description: 物流商名称
        oversea:
          type: boolean
          description: oversea
        logisticsCost:
          type: string
          description: 实际运费
        estimateLogisticsCost:
          type: string
          description: 预估运费
        logisticsCurrency:
          type: string
          description: 运费币种
        toWarehouseId:
          type: string
          description: 导入仓库ID
        toWarehouseName:
          type: string
          description: 导入仓库名称
        expectShipTime:
          type: string
          description: 预计发货时间 yyyy-MM-dd
        exclusiveInventory:
          type: string
          description: 使用专属库存 0否，1是
        paid:
          type: string
          description: 标记付款 未标记，1未付款，2已付款，3部分付款
        isSelectShelf:
          type: boolean
          description: 是否勾选了手动选择货架位 0否1是
        isExpediting:
          type: string
          description: 是否加急 1加急
      title: ShippingOrderOpenV2Vo
      x-apifox-orders:
        - shippingOrderId
        - shipSn
        - warehouseId
        - headFeeType
        - shipType
        - status
        - expectArrivalDate
        - shipTime
        - realShipTime
        - cancelTime
        - remark
        - volumeParam
        - restoreStock
        - restoreTime
        - restoreRemark
        - createUid
        - createTime
        - updateUid
        - updateTime
        - requisitionStatus
        - logistics
        - logisticsTotalSize
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
        - exclusiveInventory
        - paid
        - isSelectShelf
        - isExpediting
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOrderLogisticOpenV2Vo:
      type: object
      properties:
        estimateLogisticsCostCreateTime:
          type: string
          description: 预估物流费用创建时间 yyyy-MM-dd HH:mm:ss
        logisticsId:
          type: string
          description: 主键ID
        rateList:
          type: array
          items:
            $ref: '#/components/schemas/FbaShippingOrderLogisticRateDto'
        estimateLogisticsCostUpdateTime:
          type: string
          description: 预估物流费用更新时间 yyyy-MM-dd HH:mm:ss
        logisticsNo:
          type: string
          description: 物流商单号
        estimateOtherCostCreateTime:
          type: string
          description: 预估其它费用创建时间 yyyy-MM-dd HH:mm:ss
        trackingNo:
          type: string
          description: 物流跟踪号
        estimateOtherCostUpdateTime:
          type: string
          description: 预估其它费用更新时间 yyyy-MM-dd HH:mm:ss
        isVolumeWeight:
          type: string
          description: 是否体积重
        estimateTaxCostCreateTime:
          type: string
          description: 预估报关税费创建时间 yyyy-MM-dd HH:mm:ss
        volumeWeight:
          type: string
          description: 体积重
        estimateTaxCostUpdateTime:
          type: string
          description: 预估报关税费更新时间 yyyy-MM-dd HH:mm:ss
        logisticsCost:
          type: string
          description: 物流费用
        logisticsCostCreateTime:
          type: string
          description: 物流费用创建时间 yyyy-MM-dd HH:mm:ss
        logisticsCostCurrency:
          type: string
          description: 物流费用单位
        logisticsCostUpdateTime:
          type: string
          description: 物流费用更新时间 yyyy-MM-dd HH:mm:ss
        otherCost:
          type: string
          description: 其他费用
        otherCostCreateTime:
          type: string
          description: 其他费用创建时间 yyyy-MM-dd HH:mm:ss
        otherCostCurrency:
          type: string
          description: 其他费用单位
        otherCostUpdateTime:
          type: string
          description: 其他费用更新时间 yyyy-MM-dd HH:mm:ss
        taxCost:
          type: string
          description: 税费
        taxCostCreateTime:
          type: string
          description: 报关税费创建时间 yyyy-MM-dd HH:mm:ss
        taxCostCurrency:
          type: string
          description: 税费单位
        singleLogisticsCost:
          type: string
          description: 实际物流单价
        taxCostUpdateTime:
          type: string
          description: 报关税费更新时间 yyyy-MM-dd HH:mm:ss
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
      title: ShippingOrderLogisticOpenV2Vo
      x-apifox-orders:
        - estimateLogisticsCostCreateTime
        - logisticsId
        - rateList
        - estimateLogisticsCostUpdateTime
        - logisticsNo
        - estimateOtherCostCreateTime
        - trackingNo
        - estimateOtherCostUpdateTime
        - isVolumeWeight
        - estimateTaxCostCreateTime
        - volumeWeight
        - estimateTaxCostUpdateTime
        - logisticsCost
        - logisticsCostCreateTime
        - logisticsCostCurrency
        - logisticsCostUpdateTime
        - otherCost
        - otherCostCreateTime
        - otherCostCurrency
        - otherCostUpdateTime
        - taxCost
        - taxCostCreateTime
        - taxCostCurrency
        - singleLogisticsCost
        - taxCostUpdateTime
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
