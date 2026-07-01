# 获取Amazon移除货件报告

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/report/getFbaRemovalShipmentPage.json:
    post:
      summary: 获取Amazon移除货件报告
      deprecated: false
      description: ''
      operationId: getFbaRemovalShipmentPageUsingPOST
      tags:
        - 报告中心/报表管理
        - 数据
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
              $ref: '#/components/schemas/RemoveShipmentPageOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABRemoveShipmentOpenVo%C2%BB%C2%BB
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
                x--orders: []
                x--ignore-properties: []
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
                x--orders: []
                x--ignore-properties: []
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
                x--orders: []
                x--ignore-properties: []
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
                x--orders: []
                x--ignore-properties: []
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-apifox-folder: 报告中心/报表管理
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516607-run
components:
  schemas:
    RemoveShipmentPageOpenQo:
      type: object
      required:
        - timeType
        - startTime
        - endTime
      properties:
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
        searchType:
          type: string
          description: 搜索类型(支持搜索类型:orderId,msku,fnsku)
        shopIdList:
          type: array
          description: 店铺ID
          items:
            type: string
        searchContentList:
          type: array
          description: 搜索内容
          items:
            type: string
        timeType:
          type: string
          description: 时间类型(requestDate:请求时间;shipDate:发货时间)
        startTime:
          type: string
          description: 开始时间
        endTime:
          type: string
          description: 结束时间
      title: RemoveShipmentPageOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - searchType
        - shopIdList
        - searchContentList
        - timeType
        - startTime
        - endTime
      x--orders:
        - pageNo
        - pageSize
        - searchType
        - shopIdList
        - searchContentList
        - timeType
        - startTime
        - endTime
      x--ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«RemoveShipmentOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABRemoveShipmentOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«RemoveShipmentOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x--orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x--ignore-properties: []
      x-apifox-folder: ''
    Page«RemoveShipmentOpenVo»:
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
            $ref: '#/components/schemas/RemoveShipmentOpenVo'
      title: Page«RemoveShipmentOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x--orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x--ignore-properties: []
      x-apifox-folder: ''
    RemoveShipmentOpenVo:
      type: object
      properties:
        sellingPartnerId:
          type: string
          description: 亚马逊卖家编号
        region:
          type: string
          description: 大区，na,eu,fe
        shopId:
          type: string
          description: shopId
        marketplaceId:
          type: string
          description: marketplaceId
        orderId:
          type: string
          description: 订单号
        requestDate:
          type: string
          description: 原始请求日期
        convRequestDate:
          type: string
          description: 请求日期
        shipmentDate:
          type: string
          description: 原始发货日期
        convShipmentDate:
          type: string
          description: 发货日期
        sku:
          type: string
          description: msku
        fnsku:
          type: string
          description: fnsku
        disposition:
          type: string
          description: 是否可销售(Sellable,Unsellable)
        shippedQuantity:
          type: string
          description: 发货数量
        carrier:
          type: string
          description: 承运商
        trackingNumber:
          type: string
          description: 运单号
        removalOrderType:
          type: string
          description: 移除类型
        createDate:
          type: string
          description: 创建时间
        updateDate:
          type: string
          description: 更新时间
        setStatus:
          type: string
          description: 设置状态,0:未设置,1:已设置,2:待设置,默认:0
        matchType:
          type: string
          description: 匹配类型,0:未匹配,1:订单匹配,2:币种匹配,3:手动匹配,,默认:0
      title: RemoveShipmentOpenVo
      x-apifox-orders:
        - sellingPartnerId
        - region
        - shopId
        - marketplaceId
        - orderId
        - requestDate
        - convRequestDate
        - shipmentDate
        - convShipmentDate
        - sku
        - fnsku
        - disposition
        - shippedQuantity
        - carrier
        - trackingNumber
        - removalOrderType
        - createDate
        - updateDate
        - setStatus
        - matchType
      x--orders:
        - sellingPartnerId
        - region
        - shopId
        - marketplaceId
        - orderId
        - requestDate
        - convRequestDate
        - shipmentDate
        - convShipmentDate
        - sku
        - fnsku
        - disposition
        - shippedQuantity
        - carrier
        - trackingNumber
        - removalOrderType
        - createDate
        - updateDate
        - setStatus
        - matchType
      x--ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
