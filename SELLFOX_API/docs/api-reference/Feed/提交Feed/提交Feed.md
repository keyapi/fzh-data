# 提交Feed

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/feed/submitFeed.json:
    post:
      summary: 提交Feed
      deprecated: false
      description: ''
      operationId: submitFeedUsingPOST
      tags:
        - Feed/提交Feed
        - Feed接口
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
              $ref: '#/components/schemas/SubmitFeedOpenVo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABCreateFeedResponseOpenVo%C2%BB
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
      x-apifox-folder: Feed/提交Feed
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-86977620-run
components:
  schemas:
    SubmitFeedOpenVo:
      type: object
      required:
        - shopId
        - feedContent
        - feedType
        - contentType
      properties:
        shopId:
          type: string
          description: 店铺ID
          examples:
            - 1
        feedContent:
          type: string
          description: feedContent,上传的feed文件转成Base64字符串
        feedType:
          type: string
          description: >-
            feedType,可选值:
            POST_PRODUCT_DATA,POST_INVENTORY_AVAILABILITY_DATA,POST_PRODUCT_OVERRIDES_DATA,POST_PRODUCT_PRICING_DATA,POST_PRODUCT_IMAGE_DATA,POST_PRODUCT_RELATIONSHIP_DATA,POST_FLAT_FILE_LISTINGS_DATA,POST_ORDER_ACKNOWLEDGEMENT_DATA,POST_PAYMENT_ADJUSTMENT_DATA,POST_ORDER_FULFILLMENT_DATA,POST_INVOICE_CONFIRMATION_DATA,POST_FULFILLMENT_ORDER_REQUEST_DATA,POST_FULFILLMENT_ORDER_CANCELLATION_REQUEST_DATA,POST_FBA_INBOUND_CARTON_CONTENTS,POST_FLAT_FILE_FROM_EXCEL_FBA_CREATE_CARTON_INFO,UPLOAD_VAT_INVOICE
        contentType:
          type: string
          description: contentType,可选值：text/xml; text/plain; application/pdf
          examples:
            - 1
        feedOptions:
          type: array
          description: feed可选参数
          items:
            $ref: '#/components/schemas/FeedOptionOpenVo'
      title: SubmitFeedOpenVo
      x-apifox-orders:
        - shopId
        - feedContent
        - feedType
        - contentType
        - feedOptions
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FeedOptionOpenVo:
      type: object
      properties:
        key:
          type: string
          description: key
        value:
          type: string
          description: value
      title: FeedOptionOpenVo
      x-apifox-orders:
        - key
        - value
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«CreateFeedResponseOpenVo»:
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
          $ref: '#/components/schemas/CreateFeedResponseOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«CreateFeedResponseOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CreateFeedResponseOpenVo:
      type: object
      properties:
        feedId:
          type: string
          description: feedId
        errors:
          type: array
          description: 平台返回的异常信息
          items:
            $ref: '#/components/schemas/ApiErrorOpenVo'
      title: CreateFeedResponseOpenVo
      x-apifox-orders:
        - feedId
        - errors
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ApiErrorOpenVo:
      type: object
      properties:
        code:
          type: string
          description: code
        message:
          type: string
          description: message
        details:
          type: string
          description: details
      title: ApiErrorOpenVo
      x-apifox-orders:
        - code
        - message
        - details
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
