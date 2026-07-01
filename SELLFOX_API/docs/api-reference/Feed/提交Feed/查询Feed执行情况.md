# 查询Feed执行情况

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/feed/getFeedResponse.json:
    post:
      summary: 查询Feed执行情况
      deprecated: false
      description: ''
      operationId: getFeedResponseUsingPOST
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
              $ref: '#/components/schemas/GetFeedResponseVo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABGetFeedResponseOpenVo%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-86977618-run
components:
  schemas:
    GetFeedResponseVo:
      type: object
      required:
        - shopId
        - feedId
      properties:
        shopId:
          type: string
          description: shopId
          examples:
            - 111
        feedId:
          type: string
          description: feedId
          examples:
            - 111
      title: GetFeedResponseVo
      x-apifox-orders:
        - shopId
        - feedId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«GetFeedResponseOpenVo»:
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
          $ref: '#/components/schemas/GetFeedResponseOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«GetFeedResponseOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    GetFeedResponseOpenVo:
      type: object
      properties:
        feedId:
          type: string
          description: feedId
        feedType:
          type: string
          description: feedType
        marketplaceIds:
          type: array
          description: marketplaceIds
          items:
            type: string
        processingStatus:
          type: string
          description: processingStatus
        createdTime:
          type: string
          description: createdTime
        processingStartTime:
          type: string
          description: processingStartTime
        processingEndTime:
          type: string
          description: processingEndTime
        resultFeedDocumentId:
          type: string
          description: resultFeedDocumentId
        errors:
          type: array
          description: errors
          items:
            $ref: '#/components/schemas/ApiErrorOpenVo'
      title: GetFeedResponseOpenVo
      x-apifox-orders:
        - feedId
        - feedType
        - marketplaceIds
        - processingStatus
        - createdTime
        - processingStartTime
        - processingEndTime
        - resultFeedDocumentId
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
