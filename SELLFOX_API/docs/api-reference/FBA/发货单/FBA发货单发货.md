# FBA发货单发货

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fba/shippingOrder/confirmShip.json:
    post:
      summary: FBA发货单发货
      deprecated: false
      description: ''
      operationId: confirmShipUsingPOST
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
              $ref: '#/components/schemas/FbaShipSnsOpenVo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFbaBatchResultOpenVo%C2%BB
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
      x-apifox-folder: FBA/发货单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516611-run
components:
  schemas:
    FbaShipSnsOpenVo:
      type: object
      properties:
        shipSnList:
          type: array
          description: 发货单号
          items:
            type: string
      title: FbaShipSnsOpenVo
      x-apifox-orders:
        - shipSnList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FbaBatchResultOpenVo»:
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
          $ref: '#/components/schemas/FbaBatchResultOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FbaBatchResultOpenVo»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaBatchResultOpenVo:
      type: object
      properties:
        success:
          type: string
          description: 成功数量
        fail:
          type: string
          description: 失败数量
        failData:
          type: array
          description: 失败列表
          items:
            $ref: '#/components/schemas/ShippingOptResultOpenVo'
      title: FbaBatchResultOpenVo
      x-apifox-orders:
        - success
        - fail
        - failData
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShippingOptResultOpenVo:
      type: object
      properties:
        shipSn:
          type: string
          description: 发货单号
        allotSn:
          type: string
          description: 调拨单号
        succ:
          type: string
          description: 结果
        message:
          type: string
          description: 失败后的信息
      title: ShippingOptResultOpenVo
      x-apifox-orders:
        - shipSn
        - allotSn
        - succ
        - message
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
