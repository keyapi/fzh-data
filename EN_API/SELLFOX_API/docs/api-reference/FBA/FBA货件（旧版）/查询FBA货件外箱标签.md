# 查询FBA货件外箱标签

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/fbaShipment/batchPackageLabels.json:
    post:
      summary: 查询FBA货件外箱标签
      deprecated: false
      description: ''
      operationId: batchPackageLabelsUsingPOST
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
              $ref: '#/components/schemas/BatchPackageLabelsOpenVo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: '#/components/schemas/OpenResult'
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516615-run
components:
  schemas:
    BatchPackageLabelsOpenVo:
      type: object
      required:
        - printDetails
      properties:
        printDetails:
          type: array
          description: 打印明细
          items:
            $ref: '#/components/schemas/PrintDetailOpenVo'
        waterMark:
          type: string
          description: 是否加打made in China  支持 false和true 默认false
      title: BatchPackageLabelsOpenVo
      x-apifox-orders:
        - printDetails
        - waterMark
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    PrintDetailOpenVo:
      type: object
      required:
        - amazonShipmentId
        - pageType
        - printNum
      properties:
        amazonShipmentId:
          type: string
          description: 货件编号
        pageType:
          type: string
          description: 纸张类型
        printNum:
          type: string
          description: 数量
      title: PrintDetailOpenVo
      x-apifox-orders:
        - amazonShipmentId
        - pageType
        - printNum
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult:
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
          type: object
          description: 数据
          x-apifox-orders: []
          properties: {}
          x-apifox-ignore-properties: []
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult
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
