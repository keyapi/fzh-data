# 查询SPU

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/commodity/getCommoditySpuList.json:
    post:
      summary: 查询SPU
      deprecated: false
      description: ''
      operationId: getCommoditySpuListUsingPOST
      tags:
        - 商品/商品列表
        - 商品列表
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
              $ref: '#/components/schemas/SpuListOpenQo'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABSpuListOpenVo%C2%BB%C2%BB
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
      x-apifox-folder: 商品/商品列表
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516598-run
components:
  schemas:
    SpuListOpenQo:
      type: object
      properties:
        pageNo:
          type: string
          description: 第几页,默认1
          examples:
            - 1
        pageSize:
          type: string
          description: 每页条数,默认20
          examples:
            - 20
        fullCids:
          type: array
          description: 分类ID，多个用，隔开
          items:
            type: string
          examples:
            - 1234
        createTimeStart:
          type: string
          description: 创建时间开始于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 00:00:00'
        createTimeEnd:
          type: string
          description: 创建时间结束于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 23:59:59'
        modifiedTimeStart:
          type: string
          description: 修改时间开始于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 00:00:00'
        modifiedTimeEnd:
          type: string
          description: 修改时间结束于，yyyy-MM-dd hh:mm:ss
          examples:
            - '2022-01-01 23:59:59'
        spu:
          type: string
          description: SPU
        brandIds:
          type: array
          description: 品牌ID列表
          items:
            type: string
          examples:
            - 逗号拼接,-1为无品牌
      title: SpuListOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - fullCids
        - createTimeStart
        - createTimeEnd
        - modifiedTimeStart
        - modifiedTimeEnd
        - spu
        - brandIds
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«SpuListOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABSpuListOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«SpuListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«SpuListOpenVo»:
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
            $ref: '#/components/schemas/SpuListOpenVo'
      title: Page«SpuListOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SpuListOpenVo:
      type: object
      properties:
        spuId:
          type: string
          description: SPUID
        spu:
          type: string
          description: 商品SPU
        spuName:
          type: string
          description: 多属性商品款名
        devId:
          type: string
          description: 开发员ID
        spuImgUrl:
          type: string
          description: spu商品图片
        skuList:
          type: array
          description: SKU信息
          items:
            $ref: '#/components/schemas/CommoditySimpleOpenVo'
      title: SpuListOpenVo
      x-apifox-orders:
        - spuId
        - spu
        - spuName
        - devId
        - spuImgUrl
        - skuList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommoditySimpleOpenVo:
      type: object
      properties:
        id:
          type: string
          description: ' SKU id'
        name:
          type: string
          description: SKU商品名称
        sku:
          type: string
          description: SKU
        commodityAttributeValueRelaList:
          type: array
          description: 商品属性
          items:
            $ref: '#/components/schemas/CommodityAttributeValueRelaOpenVo'
      title: CommoditySimpleOpenVo
      x-apifox-orders:
        - id
        - name
        - sku
        - commodityAttributeValueRelaList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    CommodityAttributeValueRelaOpenVo:
      type: object
      properties:
        attributeId:
          type: string
          description: 商品属性id
        attributeValueId:
          type: string
          description: 商品属性值id
        attributeCn:
          type: string
          description: 属性中文描述
        attributeEn:
          type: string
          description: 属性英文描述
        attributeValueCn:
          type: string
          description: 属性值中文描述
        attributeValueEn:
          type: string
          description: 属性值英文描述
      title: CommodityAttributeValueRelaOpenVo
      x-apifox-orders:
        - attributeId
        - attributeValueId
        - attributeCn
        - attributeEn
        - attributeValueCn
        - attributeValueEn
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
