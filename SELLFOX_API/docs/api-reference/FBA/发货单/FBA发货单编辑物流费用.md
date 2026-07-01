# FBA发货单编辑物流费用

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/editLogisticsFee.json:
    post:
      summary: FBA发货单编辑物流费用
      deprecated: false
      description: ''
      operationId: editLogisticsFeeUsingPOST
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
              $ref: >-
                #/components/schemas/%E5%8F%91%E8%B4%A7%E5%8D%95%E7%BC%96%E8%BE%91%E5%8F%82%E6%95%B0
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OpenResult%C2%ABstring%C2%BB'
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-188252059-run
components:
  schemas:
    发货单编辑参数:
      type: object
      properties:
        orderType:
          type: string
          description: 单据类型：0-FBA货件 1-发货单
        orderSn:
          type: string
          description: 单据号
        logistics:
          type: array
          description: 单据物流信息
          items:
            $ref: '#/components/schemas/ShippingEditLogisticsOpenParam'
      title: 发货单编辑参数
      x-apifox-orders:
        - orderType
        - orderSn
        - logistics
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingEditLogisticsOpenParam:
      type: object
      properties:
        logisticsNo:
          type: string
          description: 物流商单号
          examples:
            - 1
        trackingNo:
          type: string
          description: 追踪号
          examples:
            - 1
        estimateCharged:
          type: string
          description: 预估计费重
          examples:
            - 1
        estimateSingleLogisticsCost:
          type: string
          description: 预估物流单价
          examples:
            - 1
        estimateLogisticsCost:
          type: string
          description: 预估物流费用
          examples:
            - 1
        estimateLogisticsCostCurrency:
          type: string
          description: 预估物流费用币种
          examples:
            - CNY
        estimateOtherCost:
          type: string
          description: 预估其他费用
          examples:
            - 1
        estimateOtherCostCurrency:
          type: string
          description: 预估其他费用币种
          examples:
            - CNY
        estimateTaxCost:
          type: string
          description: 预估税费
          examples:
            - 1
        estimateTaxCostCurrency:
          type: string
          description: 预估税费币种
          examples:
            - CNY
        charged:
          type: string
          description: 实际计费重(KG) 最多两位小数
          examples:
            - 1
        singleLogisticsCost:
          type: string
          description: 实际物流单价 最多两位小数
          examples:
            - 1
        logisticsCost:
          type: string
          description: 实际物流费用
          examples:
            - 1
        logisticsCostCurrency:
          type: string
          description: 实际物流费用币种
          examples:
            - CNY
        otherCost:
          type: string
          description: 实际其他费用
          examples:
            - 1
        otherCostCurrency:
          type: string
          description: 实际其他费用币种
          examples:
            - CNY
        taxCost:
          type: string
          description: 实际税费
          examples:
            - 1
        taxCostCurrency:
          type: string
          description: 实际税费币种
          examples:
            - CNY
        rateYearMonth:
          type: string
          description: 汇率所属月份，格式:yyyyMM
          examples:
            - 202201
      title: ShippingEditLogisticsOpenParam
      x-apifox-orders:
        - logisticsNo
        - trackingNo
        - estimateCharged
        - estimateSingleLogisticsCost
        - estimateLogisticsCost
        - estimateLogisticsCostCurrency
        - estimateOtherCost
        - estimateOtherCostCurrency
        - estimateTaxCost
        - estimateTaxCostCurrency
        - charged
        - singleLogisticsCost
        - logisticsCost
        - logisticsCostCurrency
        - otherCost
        - otherCostCurrency
        - taxCost
        - taxCostCurrency
        - rateYearMonth
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«string»:
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
          type: string
          description: 数据
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«string»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
