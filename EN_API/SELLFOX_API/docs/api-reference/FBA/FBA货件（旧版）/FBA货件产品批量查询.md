# FBA货件产品批量查询

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fbaShipment/batchQuery/shipmentItemList.json:
    post:
      summary: FBA货件产品批量查询
      deprecated: false
      description: ''
      operationId: shipmentItemListUsingPOST
      tags:
        - FBA/FBA货件（旧版）
        - FBA货件
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
              $ref: '#/components/schemas/ShipmentItemListBatchQueryOpenQo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABShipmentItemListGroupOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-apifox-folder: FBA/FBA货件（旧版）
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-328123046-run
components:
  schemas:
    ShipmentItemListBatchQueryOpenQo:
      type: object
      properties:
        amazonShipmentIds:
          type: array
          description: 亚马逊货件编号，最多支持50个
          items:
            type: string
        shipmentIds:
          type: array
          description: 货件ID，最多支持50个
          items:
            type: string
      title: ShipmentItemListBatchQueryOpenQo
      x-apifox-orders:
        - amazonShipmentIds
        - shipmentIds
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«ShipmentItemListGroupOpenVo»»:
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
          type: array
          description: 数据
          items:
            $ref: '#/components/schemas/ShipmentItemListGroupOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«ShipmentItemListGroupOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShipmentItemListGroupOpenVo:
      type: object
      properties:
        amazonShipmentId:
          type: string
          description: 亚马逊货件编号
        shipmentId:
          type: string
          description: 货件ID
        createTime:
          type: string
          format: date-time
          description: 创建时间
        updateTime:
          type: string
          format: date-time
          description: 更新时间
        itemList:
          type: array
          description: 货件产品明细
          items:
            $ref: >-
              #/components/schemas/%E8%B4%A7%E4%BB%B6%E4%BA%A7%E5%93%81%E6%98%8E%E7%BB%86
      title: ShipmentItemListGroupOpenVo
      x-apifox-orders:
        - amazonShipmentId
        - shipmentId
        - createTime
        - updateTime
        - itemList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    货件产品明细:
      type: object
      properties:
        id:
          type: string
          description: ID
        sku:
          type: string
          description: sku
        fnSku:
          type: string
          description: fnSku
        asin:
          type: string
          description: asin
        condition:
          type: string
          description: 物品状态
        commodityId:
          type: string
          description: 商品Id
        commodityName:
          type: string
          description: SKU名称
        commoditySku:
          type: string
          description: SKU
        quantity:
          type: string
          description: 申报数量
        quantityShipped:
          type: string
          description: 发货数量
        quantityFromShipOrder:
          type: string
          description: 来自发货单的发货量
        quantityReceived:
          type: string
          description: 签收量
        quantityInCase:
          type: string
          description: 单箱数量
        caseNum:
          type: string
          description: 箱数(针对原厂包装)
        planId:
          type: string
          description: 发货计划ID
        planSn:
          type: string
          description: 发货计划编号
        itemType:
          type: string
          description: '货件商品类型 0默认 1追加 '
        cartonLength:
          type: string
          description: 箱规——长
        cartonWidth:
          type: string
          description: 箱规——宽
        cartonHeight:
          type: string
          description: 箱规——高
        cartonWeight:
          type: string
          description: 单箱重量
        firstSignDate:
          type: string
          description: 首次签收时间
        signedList:
          type: array
          description: 货件签收量
          items:
            $ref: '#/components/schemas/%E8%B4%A7%E4%BB%B6%E7%AD%BE%E6%94%B6%E9%87%8F'
        childSku:
          type: array
          description: 子SKU
          items:
            $ref: '#/components/schemas/%E5%AD%90SKU'
        shipSnList:
          type: array
          description: 发货单编号
          items:
            type: string
        shipCount:
          type: string
          description: 总调拨量
      title: 货件产品明细
      x-apifox-orders:
        - id
        - sku
        - fnSku
        - asin
        - condition
        - commodityId
        - commodityName
        - commoditySku
        - quantity
        - quantityShipped
        - quantityFromShipOrder
        - quantityReceived
        - quantityInCase
        - caseNum
        - planId
        - planSn
        - itemType
        - cartonLength
        - cartonWidth
        - cartonHeight
        - cartonWeight
        - firstSignDate
        - signedList
        - childSku
        - shipSnList
        - shipCount
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    子SKU:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        num:
          type: string
        sku:
          type: string
      title: 子SKU
      x-apifox-orders:
        - id
        - name
        - num
        - sku
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    货件签收量:
      type: object
      properties:
        signDate:
          type: string
        signNum:
          type: string
      title: 货件签收量
      x-apifox-orders:
        - signDate
        - signNum
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
