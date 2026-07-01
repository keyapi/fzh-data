# ABA搜索词

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/cpc/searchTerms/pageList.json:
    post:
      summary: ABA搜索词
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_15
      tags:
        - 广告/其他报告
        - 广告-其他报告-ABA搜索词报告
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
              $ref: '#/components/schemas/SearchTermsPageOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABSearchTermsOpenVo%C2%BB%C2%BB
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
      x-order: '1'
      x-apifox-folder: 广告/其他报告
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-426587990-run
components:
  schemas:
    SearchTermsPageOpenQo:
      type: object
      required:
        - marketplaceId
        - startDate
        - endDate
        - reportType
      properties:
        marketplaceId:
          type: string
          description: |-
            站点ID，站点国家限制：美国、加拿大、墨西哥、巴西、英国、德国、法国、意大利、
            西班牙、荷兰、瑞典、土耳其、沙特阿拉伯、印度、日本、澳大利亚、新加坡、阿联酋
        startDate:
          type: string
          description: 开始日期：yyyy-MM-dd
          examples:
            - '2026-01-01'
        endDate:
          type: string
          description: 结束日期：yyyy-MM-dd
          examples:
            - '2026-01-01'
        reportType:
          type: string
          description: >-
            时间维度，可选值：day（按天） week（按周） month（月度） quarter（季度）

            day：startDate和endDate应该为同一天

            week：startDate和endDate相差应该为六天，且startDate应该为周日

            month：startDate应该为一个月的第一天，endDate应该为该月的最后一天

            quarter：startDate应该为一个季度的第一天，endDate应该为该季度的最后一天，1、2、3月为第一个季度Q1，Q2、Q3、Q4同理
        pageNo:
          type: string
          description: 第几页，默认1
          examples:
            - 1
        pageSize:
          type: string
          description: 每页条数，默认100，最大1000
          examples:
            - 100
        searchTermList:
          type: array
          description: 搜索词筛选，最多支持200个搜索词
          items:
            type: string
      title: SearchTermsPageOpenQo
      x-apifox-orders:
        - marketplaceId
        - startDate
        - endDate
        - reportType
        - pageNo
        - pageSize
        - searchTermList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«SearchTermsOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABSearchTermsOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«SearchTermsOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«SearchTermsOpenVo»:
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
            $ref: '#/components/schemas/SearchTermsOpenVo'
      title: Page«SearchTermsOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SearchTermsOpenVo:
      type: object
      properties:
        marketplaceId:
          type: string
          description: 站点ID
        searchTerm:
          type: string
          description: 搜索词
        searchFrequencyRank:
          type: string
          description: 搜索词频率排名
        lastSearchFrequencyRank:
          type: string
          description: 排名环比
        topClickShare:
          type: string
          description: 前3 ASIN点击量占比
        topConversionShare:
          type: string
          description: 前3 ASIN转化占比
        clickedAsinOne:
          type: string
          description: TOP1 ASIN
        clickedAsinTwo:
          type: string
          description: TOP2 ASIN
        clickedAsinThree:
          type: string
          description: TOP3 ASIN
        clickedItemNameOne:
          type: string
          description: TOP1 商品名称
        clickedItemNameTwo:
          type: string
          description: TOP2 商品名称
        clickedItemNameThree:
          type: string
          description: TOP3 商品名称
        clickShareOne:
          type: string
          description: TOP1 点击份额
        clickShareTwo:
          type: string
          description: TOP2 点击份额
        clickShareThree:
          type: string
          description: TOP3 点击份额
        conversionShareOne:
          type: string
          description: TOP1 转化份额
        conversionShareTwo:
          type: string
          description: TOP2 转化份额
        conversionShareThree:
          type: string
          description: TOP3 转化份额
        startDate:
          type: string
          description: 开始日期
        endDate:
          type: string
          description: 结束日期
      title: SearchTermsOpenVo
      x-apifox-orders:
        - marketplaceId
        - searchTerm
        - searchFrequencyRank
        - lastSearchFrequencyRank
        - topClickShare
        - topConversionShare
        - clickedAsinOne
        - clickedAsinTwo
        - clickedAsinThree
        - clickedItemNameOne
        - clickedItemNameTwo
        - clickedItemNameThree
        - clickShareOne
        - clickShareTwo
        - clickShareThree
        - conversionShareOne
        - conversionShareTwo
        - conversionShareThree
        - startDate
        - endDate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
