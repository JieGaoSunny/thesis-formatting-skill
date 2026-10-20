# Thesis formatting audit

- Profile: `apple-university-thesis`
- Document SHA-256: `7c0062884a840c70c3f5e4a6080b03ca057be3519d08a95253e6388a738767ce`
- Errors: 0
- Violations: 29
- Warnings: 314

| Severity | Rule | Location | Message | Before | After |
|---|---|---|---|---|---|
| violation | `FIELD.TOC.REQUIRED` | `document` | Required generated field is missing. | false | TOC \\o "1-3" \\h \\z \\u |
| violation | `PAGE.MARGIN.BODY` | `section:1` | Body margins do not match the selected profile. | {"bottom":30,"left":20,"right":20,"top":30} | {"bottom":30,"left":30,"right":30,"top":30} |
| violation | `PAGE.PAPER.SIZE` | `section:1` | Paper dimensions do not match the selected profile. | {"height_mm":279.4,"width_mm":215.9} | {"height_mm":297,"width_mm":210} |
| violation | `HEADER.FOOTER.PAGE_NUMBER` | `section:2` | No generated page-number field was found for this section. | false | true |
| violation | `PAGE.MARGIN.BODY` | `section:2` | Body margins do not match the selected profile. | {"bottom":30,"left":20,"right":20,"top":30} | {"bottom":30,"left":30,"right":30,"top":30} |
| violation | `PAGE.PAPER.SIZE` | `section:2` | Paper dimensions do not match the selected profile. | {"height_mm":279.4,"width_mm":215.9} | {"height_mm":297,"width_mm":210} |
| violation | `PAGE.SECTION.START` | `section:2` | Section start does not match the selected profile. | continuous | nextPage |
| warning | `HEADER.FOOTER.LINKING` | `section:2` | Header or footer relationship target breaks required section linking. | ["header","footer"] | linked to previous |
| violation | `HEADER.FOOTER.HEADER_SOURCE` | `section:3` | Header content does not match the configured source. | missing or unrelated header source | current_heading_1 |
| violation | `HEADER.FOOTER.PAGE_NUMBER` | `section:3` | No generated page-number field was found for this section. | false | true |
| violation | `PAGE.MARGIN.BODY` | `section:3` | Body margins do not match the selected profile. | {"bottom":30,"left":20,"right":20,"top":30} | {"bottom":30,"left":30,"right":30,"top":30} |
| violation | `PAGE.PAPER.SIZE` | `section:3` | Paper dimensions do not match the selected profile. | {"height_mm":279.4,"width_mm":215.9} | {"height_mm":297,"width_mm":210} |
| warning | `HEADER.FOOTER.LINKING` | `section:3` | Header or footer relationship target breaks required section linking. | ["header","footer"] | linked to previous |
| violation | `HEADER.FOOTER.PAGE_NUMBER` | `section:4` | No generated page-number field was found for this section. | false | true |
| violation | `PAGE.MARGIN.BODY` | `section:4` | Body margins do not match the selected profile. | {"bottom":30,"left":20,"right":20,"top":30} | {"bottom":30,"left":30,"right":30,"top":30} |
| violation | `PAGE.PAPER.SIZE` | `section:4` | Paper dimensions do not match the selected profile. | {"height_mm":279.4,"width_mm":215.9} | {"height_mm":297,"width_mm":210} |
| warning | `HEADER.FOOTER.LINKING` | `section:4` | Header or footer relationship target breaks required section linking. | ["header","footer"] | linked to previous |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:1` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:2` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:5` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:6` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:8` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:9` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:17` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| violation | `NUMBERING.MANUAL_HEADING` | `paragraph:19` | Heading number is typed manually instead of generated. | 第一章 | automatic numbering |
| warning | `STYLE.DIRECT_FORMATTING` | `paragraph:19` | Direct formatting may override the selected profile style. | {"paragraph_properties":0,"run_properties":1} | {"paragraph_properties":0,"run_properties":0} |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:20` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| violation | `STYLE.ROLE.MAPPING` | `paragraph:21` | Paragraph does not use the profile style for its semantic role. | UnreliableHeading | ["AppleHeading2","苹果大学标题2"] |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:22` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:23` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:25` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:26` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:28` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:29` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:31` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:33` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:34` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| violation | `FIGURE.CAPTION.POSITION` | `paragraph:36` | Figure must have a caption immediately below it. | false | caption below |
| violation | `FIGURE.DIMENSIONS.MAX_WIDTH` | `paragraph:36` | Figure exceeds the maximum profile width. | 180 | 150 |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:38` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:39` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:40` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:41` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:42` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:43` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:44` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:45` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:46` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:47` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:48` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:49` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:50` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:51` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:52` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:53` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:54` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:55` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:56` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:57` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:58` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:60` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:61` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:63` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:64` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:66` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:68` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:69` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:73` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:74` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:75` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:76` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:77` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:78` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:79` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:80` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:81` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:82` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:83` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:84` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:85` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:86` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:87` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:88` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:89` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:91` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:92` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:94` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:95` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:96` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:97` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:100` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:101` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:103` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:105` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:108` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:109` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:110` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:111` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:112` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| violation | `REFERENCE.PARAGRAPH_FORMAT` | `paragraph:113` | Reference spacing or hanging indent does not match the profile. | {"hanging_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} | {"hanging_indent_mm":10,"line_spacing":{"type":"exact","value_pt":16},"space_after_pt":0,"space_before_pt":0} |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:116` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:117` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:118` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:120` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:121` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:122` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:123` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:124` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:125` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:126` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:127` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:128` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:129` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:130` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:131` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:132` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:133` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:134` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:135` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:136` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:137` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:138` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:139` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:140` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:141` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:142` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:143` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:144` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:146` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:147` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:148` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:149` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:150` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:151` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:152` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:153` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:154` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:155` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:156` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:157` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:158` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:159` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:160` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:161` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:162` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:163` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:164` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:165` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:166` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:167` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:168` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:169` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:170` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:171` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:172` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:173` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:174` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:175` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:176` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:177` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:178` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:179` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:180` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:181` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:182` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:183` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:184` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:185` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:186` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:187` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:188` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:189` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:190` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:191` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:192` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:193` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:194` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:195` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:196` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:197` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:198` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:199` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:200` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:201` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:202` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:203` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:204` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:205` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:206` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:207` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:208` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:209` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:210` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:211` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:212` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:213` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:214` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:215` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:216` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:217` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:218` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:219` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:220` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:221` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:222` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:223` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:224` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:225` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:226` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:227` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:228` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:229` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:230` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:231` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:232` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:233` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:234` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:235` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:236` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:237` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:238` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:239` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:240` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:241` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:242` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:243` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:244` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:245` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:246` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:247` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:248` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:249` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:250` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:251` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:252` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:253` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:254` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:255` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:256` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:257` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:258` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:259` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:260` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:261` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:262` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:263` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:264` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:265` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:266` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:267` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:268` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:269` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:270` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:271` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:272` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:273` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:274` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:275` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:276` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:277` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:278` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:279` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:280` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:281` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:282` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:283` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:284` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:285` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:286` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:287` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:288` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:289` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:290` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:291` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:292` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:293` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:294` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:295` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:296` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:297` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:298` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:299` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:300` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:301` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:302` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:303` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:304` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:305` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:306` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:307` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:308` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:309` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:310` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:311` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:312` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:313` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:314` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:315` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:316` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:317` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:318` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:319` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:320` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:321` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:322` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:323` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:324` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:325` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:326` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:327` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:328` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:329` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:330` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:331` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:332` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:333` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:334` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:335` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:336` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:338` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:339` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:340` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:341` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:342` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:343` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:344` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:345` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:346` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:347` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:348` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:349` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:350` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:351` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:352` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:353` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:354` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| warning | `STYLE.DIRECT_FORMATTING` | `paragraph:355` | Direct formatting may override the selected profile style. | {"paragraph_properties":1,"run_properties":0} | {"paragraph_properties":0,"run_properties":0} |
| warning | `SEMANTIC.AMBIGUOUS_ROLE` | `paragraph:356` | Paragraph role is ambiguous and requires review. | ambiguous | — |
| violation | `TABLE.BORDERS.THREE_LINE` | `table:1` | Table does not use the required three-line border model. | other | three_line |
| violation | `TABLE.REPEAT_HEADER` | `table:1` | Table header row is not configured to repeat. | false | true |
| violation | `TABLE.ROW_SPLIT` | `table:1` | Table rows are allowed to split across pages. | 4 | 0 |
| violation | `STYLE.DEFINITION` | `part:word/styles.xml` | Profile style definition contains incorrect formatting. | {"paragraph":{"alignment":"start","first_line_chars":0,"hanging_indent_mm":0,"keep_with_next":false,"left_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"page_break_before":false,"space_after_pt":0,"space_before_pt":0},"role":"reference","run":{"bold":false,"font_latin":"Liberation Serif","font_zh":"Noto Serif CJK SC","italic":false,"size_pt":10.5},"style_id":"AppleReference"} | {"paragraph":{"alignment":"start","first_line_chars":0,"hanging_indent_mm":10,"keep_with_next":false,"left_indent_mm":0,"line_spacing":{"type":"exact","value_pt":16},"page_break_before":false,"space_after_pt":0,"space_before_pt":0},"role":"reference","run":{"bold":false,"font_latin":"Liberation Serif","font_zh":"Noto Serif CJK SC","italic":false,"size_pt":10.5},"style_id":"AppleReference"} |
| violation | `STYLE.DEFINITION` | `part:word/styles.xml` | Profile style definition contains incorrect formatting. | {"paragraph":{"alignment":"both","first_line_chars":2,"hanging_indent_mm":0,"keep_with_next":false,"left_indent_mm":0,"line_spacing":{"type":"multiple","value":1.5},"page_break_before":false,"space_after_pt":9,"space_before_pt":0},"role":"body","run":{"bold":false,"font_latin":"Arial","font_zh":"SimSun","italic":false,"size_pt":12},"style_id":"AppleBody"} | {"paragraph":{"alignment":"both","first_line_chars":2,"hanging_indent_mm":0,"keep_with_next":false,"left_indent_mm":0,"line_spacing":{"type":"exact","value_pt":20},"page_break_before":false,"space_after_pt":0,"space_before_pt":0},"role":"body","run":{"bold":false,"font_latin":"Liberation Serif","font_zh":"Noto Serif CJK SC","italic":false,"size_pt":12},"style_id":"AppleBody"} |
