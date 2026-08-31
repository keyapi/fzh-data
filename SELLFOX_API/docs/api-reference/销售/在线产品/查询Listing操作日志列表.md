# 查询Listing操作日志列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/order/api/product/getProductChangeRecordList.json:
    post:
      summary: 查询Listing操作日志列表
      deprecated: false
      description: 用户获取自身亚马逊店铺产品的操作日志
      operationId: apiProductChangeRecordListUsingPOST
      tags:
        - 销售/在线产品
        - 销售
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
              $ref: '#/components/schemas/ProductChangeRecordPageListOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABProductChangeRecordPageListOpenVo%C2%BB%C2%BB
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
      x-order: '5'
      x-apifox-folder: 销售/在线产品
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-431277213-run
components:
  schemas:
    ProductChangeRecordPageListOpenQo:
      type: object
      required:
        - dateType
        - startDate
        - endDate
      properties:
        shopIdList:
          type: array
          description: 店铺ID
          items:
            type: string
        createIdList:
          type: array
          description: 创建人ID
          items:
            type: string
        changeTypeList:
          type: array
          description: 变更类型 1、价格 2、库存 3、Listing 4、B2B价格 5、安全与合规 6、运输 7、最低/最高价
          items:
            type: string
        status:
          type: string
          description: 变更状态 1：处理中，2：成功，3：失败
        dateType:
          type: string
          description: 时间类型 更新时间 createTime、创建时间 updateTime
        startDate:
          type: string
          description: 开始时间，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 00:00:00'
        endDate:
          type: string
          description: 结束时间，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 00:00:00'
        pageNo:
          type: string
          description: 第几页 默认1
        pageSize:
          type: string
          description: 每页大小 默认20
      title: ProductChangeRecordPageListOpenQo
      x-apifox-orders:
        - shopIdList
        - createIdList
        - changeTypeList
        - status
        - dateType
        - startDate
        - endDate
        - pageNo
        - pageSize
      x--orders:
        - shopIdList
        - createIdList
        - changeTypeList
        - status
        - dateType
        - startDate
        - endDate
        - pageNo
        - pageSize
      x--ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ProductChangeRecordPageListOpenVo»»:
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
          $ref: >-
            #/components/schemas/Page%C2%ABProductChangeRecordPageListOpenVo%C2%BB
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ProductChangeRecordPageListOpenVo»»
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
    Page«ProductChangeRecordPageListOpenVo»:
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
            $ref: '#/components/schemas/ProductChangeRecordPageListOpenVo'
      title: Page«ProductChangeRecordPageListOpenVo»
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
    ProductChangeRecordPageListOpenVo:
      type: object
      properties:
        asin:
          type: string
        beginTime:
          type: string
        changeContent:
          type: string
        changeFrom:
          type: string
        changeType:
          type: string
        createId:
          type: string
        createName:
          type: string
        currency:
          type: string
        endTime:
          type: string
        failReason:
          type: string
        fnsku:
          type: string
        fulfillmentChannel:
          type: string
        id:
          type: integer
          format: int64
        mainImage:
          type: string
        marketplaceId:
          type: string
        msku:
          type: string
        operateNote:
          type: string
        productId:
          type: string
        shopId:
          type: string
        shopName:
          type: string
        siteName:
          type: string
        status:
          type: string
        switchFulfillmentTo:
          type: string
      title: ProductChangeRecordPageListOpenVo
      x-apifox-orders:
        - asin
        - beginTime
        - changeContent
        - changeFrom
        - changeType
        - createId
        - createName
        - currency
        - endTime
        - failReason
        - fnsku
        - fulfillmentChannel
        - id
        - mainImage
        - marketplaceId
        - msku
        - operateNote
        - productId
        - shopId
        - shopName
        - siteName
        - status
        - switchFulfillmentTo
      x--orders:
        - asin
        - beginTime
        - changeContent
        - changeFrom
        - changeType
        - createId
        - createName
        - currency
        - endTime
        - failReason
        - fnsku
        - fulfillmentChannel
        - id
        - mainImage
        - marketplaceId
        - msku
        - operateNote
        - productId
        - shopId
        - shopName
        - siteName
        - status
        - switchFulfillmentTo
      x--ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
