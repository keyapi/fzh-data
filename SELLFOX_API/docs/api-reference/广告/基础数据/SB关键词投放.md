# SB关键词投放

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/cpc/manageData/sbKeyword.json:
    post:
      summary: SB关键词投放
      deprecated: false
      description: ''
      operationId: sbKeywordUsingPOST
      tags:
        - 广告/基础数据
        - 广告-基础数据
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
              $ref: '#/components/schemas/ManageDataWithGroupReqVo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABManageDataBaseRespVo%C2%ABManageDataSbKeyword%C2%BB%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-order: '12'
      x-apifox-folder: 广告/基础数据
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-367482265-run
components:
  schemas:
    ManageDataWithGroupReqVo:
      type: object
      required:
        - shopId
      properties:
        shopId:
          type: string
          description: 店铺id
        state:
          type: string
          description: 运行状态, 开启:enabled, 暂停:paused, 归档:archived, 不传默认查询全部
        campaignId:
          type: string
          description: 广告活动id
        pageSize:
          type: string
          description: 每页条数, 不传默认100, 支持100~1000
        groupId:
          type: string
          description: 广告组id
        nextToken:
          type: string
          description: 分页游标, 为空则查第一页, 使用该值查询下一页的数据(此时其余条件均失效使用第一页时的条件)
      title: ManageDataWithGroupReqVo
      x-apifox-orders:
        - shopId
        - state
        - campaignId
        - pageSize
        - groupId
        - nextToken
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«ManageDataBaseRespVo«ManageDataSbKeyword»»:
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
            #/components/schemas/ManageDataBaseRespVo%C2%ABManageDataSbKeyword%C2%BB
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«ManageDataBaseRespVo«ManageDataSbKeyword»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ManageDataBaseRespVo«ManageDataSbKeyword»:
      type: object
      properties:
        nextToken:
          type: string
          description: 分页游标, 有值则说明有下一页, 使用该值查询下一页的数据(此时其余条件均失效使用第一页时的条件, 超时时间1分钟)
        itemList:
          type: array
          description: 数据集
          items:
            $ref: '#/components/schemas/ManageDataSbKeyword'
      title: ManageDataBaseRespVo«ManageDataSbKeyword»
      x-apifox-orders:
        - nextToken
        - itemList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ManageDataSbKeyword:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺id
        state:
          type: string
          description: 运行状态
        campaignId:
          type: string
          description: 广告活动id
        groupId:
          type: string
          description: 广告组id
        keywordId:
          type: string
          description: 关键词id
        keywordText:
          type: string
          description: 关键词文本
        bid:
          type: string
          description: 竞价
        matchType:
          type: string
          description: 匹配类型(exact精确，broad广泛，phrase词组，theme主题)
      title: ManageDataSbKeyword
      x-apifox-orders:
        - shopId
        - state
        - campaignId
        - groupId
        - keywordId
        - keywordText
        - bid
        - matchType
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
