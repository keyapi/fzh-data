# 打印FNSKU标签

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/print/fnskuLabel.json:
    post:
      summary: 打印FNSKU标签
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_6
      tags:
        - 工具/打印标签
        - 打印模板
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
              $ref: '#/components/schemas/PrintFnskuLabelQo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: '#/components/schemas/OpenResult%C2%ABstring%C2%BB'
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
      x-apifox-folder: 工具/打印标签
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-276159768-run
components:
  schemas:
    PrintFnskuLabelQo:
      type: object
      required:
        - templateName
        - detailsDataList
        - separatorConfigList
        - separatorPosition
      properties:
        templateName:
          type: string
          description: 模板名称
          examples:
            - 欧代标签50*60-系统模板
        detailsDataList:
          type: array
          description: 商品详细信息列表。
          items:
            $ref: '#/components/schemas/DetailsData'
        separatorConfigList:
          type: array
          description: 分隔页配置，用于定义标签的显示内容
          items:
            $ref: '#/components/schemas/SeparatorConfig'
        separatorPosition:
          type: integer
          format: int32
          description: 分隔符位置（1：分隔页在开头；2：分隔页在结尾；3：分隔页在开头和结尾）。
          examples:
            - 1
      title: PrintFnskuLabelQo
      x-apifox-orders:
        - templateName
        - detailsDataList
        - separatorConfigList
        - separatorPosition
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SeparatorConfig:
      type: object
      properties:
        label:
          type: string
          description: 标签名称 序号、FNSKU、MSKU、ASIN、标题、SKU、品名、数量、货架位、业务员、店铺、商品备注
        lineShow:
          type: integer
          format: int32
          description: 默认为0无限展示，值为1展示1行，为2展示2行，以此类推，最大为10
      title: SeparatorConfig
      x-apifox-orders:
        - label
        - lineShow
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    DetailsData:
      type: object
      required:
        - shopId
        - msku
        - printNum
      properties:
        shopId:
          type: integer
          format: int32
          description: 店铺ID
        msku:
          type: string
          description: MSKU 编码
        productInfo:
          type: string
          description: 商品信息描述
        agentInfo:
          type: string
          description: 代理信息
        manufacturerInfo:
          type: string
          description: 生产商信息
        earImg:
          type: string
          description: 认证图片
        printNum:
          type: integer
          format: int32
          description: 打印数量
          examples:
            - 1
      title: DetailsData
      x-apifox-orders:
        - shopId
        - msku
        - productInfo
        - agentInfo
        - manufacturerInfo
        - earImg
        - printNum
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
