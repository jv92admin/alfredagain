-- Migration 032: Deduplicate ingredients (reviewed merges only)
--
-- Merges 224 approved groups (435 duplicate IDs)
-- Skipped 26 groups, 40 marked unsure
--
-- Generated from reviewed dedupe analysis in docs/ideas/dedupe.txt
-- Each group was reviewed with CONTEXT/RISK/VERDICT annotations.
-- Only APPROVE verdicts are included. UUIDs that also appear in
-- SKIP/UNSURE groups have been excluded for safety.

BEGIN;

-- Mapping table: duplicate_id -> canonical_name
CREATE TEMP TABLE dedupe_map (
    duplicate_id UUID NOT NULL,
    canonical_name TEXT NOT NULL
);

INSERT INTO dedupe_map (duplicate_id, canonical_name) VALUES
    ('7b09844a-5cd3-4677-84c4-6240f0cbd7ac', 'acai berry'),
    ('8146957e-436c-461e-8808-3abe7f631998', 'acai berry'),
    ('abe906e4-f961-45e6-83c1-a5500a272899', 'apricot'),
    ('12a743a5-d858-4520-ba2d-b3a50747843a', 'apricot'),
    ('c1e6441f-4747-4f6e-95a5-71b1cb4573cb', 'adzuki beans'),
    ('3a7cb36d-18af-44f7-80c3-6694c386aba3', 'adzuki beans'),
    ('98f152de-314e-4411-a3bc-c6bd963e524e', 'almond'),
    ('f2d1247f-2ecd-4731-9f65-afb103dcca24', 'almond'),
    ('4cac7c73-4ae9-4b4f-96d0-48bc36cf7fd9', 'almond flour'),
    ('6a0e4b84-b794-44fd-93c4-09950c9e6f98', 'almond oil'),
    ('40724674-04e7-4b6c-beaa-0c208b6db5ca', 'almond extract'),
    ('23945c14-7b6d-4ff7-b55c-be15a92d6547', 'almond butter'),
    ('32769f0b-f996-4d9b-8bf2-08b291ef926a', 'almond-cashew butter'),
    ('ea70102c-6090-4fb6-b9fa-6ba2548c67a7', 'agar agar'),
    ('af783c8d-c12f-415e-bd14-d19e5e09835a', 'agar agar'),
    ('60c535bf-110e-4242-a802-305dccc9415a', 'amaranth'),
    ('2deda804-ee0c-455b-8c5e-908cf4c468d4', 'amaranth'),
    ('cfcf9ab1-ce9f-4cf1-b368-0351905e4238', 'amaranth flour'),
    ('a208f7bf-5f4b-41d5-9f7c-0e9cfbe34663', 'anchovy'),
    ('128a15fb-0aff-4598-bc2b-d9a09a12e2d3', 'anchovy'),
    ('6e2fc617-cbef-40fa-afda-6fbd25878bf1', 'anise extract'),
    ('57e38d2d-32d9-4992-bd26-e7719888e1c4', 'apple sauce'),
    ('4d0af908-f2c5-4ac2-9789-954c208b2409', 'apple sauce'),
    ('59e4ca25-8450-4651-8ac2-f231e36ab632', 'arrowroot'),
    ('42d78ee4-ab48-43c2-995b-07fd3475c452', 'arrowroot'),
    ('c12180e5-67a3-4c10-98b5-89fe12462028', 'arrowroot'),
    ('93b4ab81-7fca-443a-943c-e16154f0122a', 'aged appenzeller'),
    ('70df0092-1bde-4295-bafb-94b7243101e2', 'aged appenzeller'),
    ('014ade64-ee4f-44f2-baac-7e4138dce3b2', 'akawi cheese'),
    ('36aa0be6-0863-4663-b2c6-3a9627e34688', 'akawi cheese'),
    ('60a4772e-813e-4253-b597-501085f2f002', 'aji panca'),
    ('ff520236-25a8-4e69-adff-2c5b96b49f70', 'aji panca'),
    ('50504e5b-92db-47cf-bc4b-7df79fe1049d', 'amchur'),
    ('67988e2b-397d-437b-bd6e-1c757e16470a', 'amchur'),
    ('10a16615-1932-42c8-875c-630fb006669b', 'blueberry'),
    ('2dfa6c12-b1df-4fa2-8492-63e55798bdd1', 'blueberry'),
    ('3902d6ad-f68f-4aa9-ac0e-00db6a1c6b81', 'blackberry'),
    ('54c610f3-d528-4193-a74b-d23c1b1f7500', 'blackberry'),
    ('2ebf9d76-5fac-4e59-9af7-c167edfa5db2', 'boysenberry'),
    ('3e6628ce-3016-46e9-9275-14ae77f6c50d', 'boysenberry'),
    ('9b002da6-13f1-42f5-b373-b1cf66d7d3e9', 'barberry'),
    ('bdf3a3bc-06c5-44d8-90d1-b72981c0e2df', 'barberry'),
    ('025c7744-64c1-41d4-af3c-330495aceca7', 'bilberry'),
    ('8d1fe517-64a1-4334-afb2-fe9bf8562106', 'bilberry'),
    ('0f226345-d4b5-45ab-ae0d-4ce142404240', 'bay leaf'),
    ('66edf312-fea8-4953-a9d0-ecc361a30ff5', 'bay leaf'),
    ('462f3093-d9bb-4a4a-8b76-9d6f41740ad5', 'bao'),
    ('f96226e2-d8b2-4ad2-beac-4c6ae94f0b1f', 'bao'),
    ('5c73c949-5d28-415c-9caa-91dc9d9c2f1b', 'black-eyed peas'),
    ('d196a730-a02e-4d53-a6ba-13ac4257f731', 'black-eyed peas'),
    ('1ec84a84-89f4-4ce6-a840-708dc4da812e', 'beet'),
    ('730ad668-9767-4577-9c00-a1c9602f15d9', 'beet'),
    ('029a844b-d967-46ea-8473-15fccb19810e', 'brisket'),
    ('07cfb8a8-7224-4cf6-a5ad-b0c07b76b7a7', 'brisket'),
    ('f3995631-9956-4150-a5a4-98a7b43e5bbd', 'brisket flat'),
    ('85423dcd-e908-4fb7-9d6f-1e10a48468b9', 'brisket flat'),
    ('a80faefa-e5e6-4798-b72f-110a370bebc4', 'brisket flat'),
    ('b510b9a7-86b8-4928-9fff-c091d8143f96', 'brisket point'),
    ('a234bfba-e4dc-4fd5-93be-5a70f4f8bd94', 'brisket point'),
    ('d2b9f682-f65c-434c-af00-da919e3cc3de', 'brisket point'),
    ('d8c6feed-e971-4325-b6b8-6e25fd25f027', 'beef bone'),
    ('c2b03fd4-d022-40f8-ae64-92d7e3d98af2', 'beef bone'),
    ('37a1fe6f-3dee-4f13-9243-d8901cb51aa5', 'beef bone'),
    ('35f32571-68b2-4a29-8292-123a1d16b5a6', 'beef fat'),
    ('b47d7600-4e1b-4eda-a33a-02d79733ec3f', 'beef fat'),
    ('a92dc1ca-766c-4306-8276-ab1ea747ccc9', 'beef fat'),
    ('f3f62ae5-d427-432d-b730-cc36b0d53501', 'beef short ribs'),
    ('cd2aadde-d81d-4ec6-85bf-9b2cfd7628bd', 'beef short ribs'),
    ('4e9850d2-0a76-4344-9aa9-b172f1da13e2', 'barbecue sauce'),
    ('4c7845af-8b66-4ca5-90cc-bd247ae5d71e', 'barbecue sauce'),
    ('4287604b-d40c-42e8-b5c0-1fe9a917fa92', 'bulgur'),
    ('fb852198-f049-478f-bcee-7e5336467916', 'bulgur'),
    ('89c2b25f-0d58-465e-be45-a2cb56aeed98', 'carrot'),
    ('743fd21e-08ee-4741-b48f-d2f4254bd45c', 'carrot'),
    ('25355d42-bd01-4960-9ef0-9753ba542446', 'cheddar'),
    ('55c89395-f484-45dc-858f-41754a51240b', 'cucumber'),
    ('9fc79391-8e5b-44a5-89d2-8cbbb8079107', 'cucumber'),
    ('1b01decc-dc4c-42d7-bab6-872e348c2b2f', 'canned tomatoes'),
    ('2296b013-927e-4b2f-b811-3ef718ef1cbc', 'canned tomatoes'),
    ('c48e6303-96b6-4dc5-83a3-0fec17387a68', 'crème fraîche'),
    ('005ab669-855b-42dd-9a2a-d9f4e9256511', 'cayenne pepper'),
    ('f4f1c1d1-4cc1-44c8-b2fb-758be92a4c6a', 'cayenne pepper'),
    ('f73c2c76-eab4-4f86-b853-ffac5ed8d861', 'cayenne pepper'),
    ('06f80469-fe66-41f5-9996-6ea34252bc19', 'cabbage'),
    ('c3f484ff-e9a5-451b-b511-8ffaf5545b31', 'chipotle'),
    ('2b2e79e4-1de1-4b2a-83cd-206288b96381', 'chipotle'),
    ('01631ed5-3cc8-4c5e-96b8-3ef623af4b3c', 'chipotle'),
    ('1e76171c-708d-4238-9da7-0ad3eeb9e831', 'cilantro'),
    ('edec8de6-ef98-4fad-9284-01a07d57b1ad', 'chicken gizzard'),
    ('9f4f83eb-49ec-45fd-9ff6-10981ff7b8d8', 'chicken gizzard'),
    ('69c629fe-06e4-421d-a8fc-980e7968a21d', 'chicken heart'),
    ('222f4bdd-ffee-4340-950f-93b0980c80da', 'chicken heart'),
    ('106e0ba6-f105-4384-b46d-fe46c4781558', 'chicken egg'),
    ('d46de838-fac6-4e3c-8d22-afda548cb2e5', 'chicken egg'),
    ('0a6551a7-387e-43b1-bc68-3cfa491b55dc', 'cranberry'),
    ('fa516b65-eb16-4df4-973c-0ce50168f95c', 'cranberry'),
    ('c8dbba91-f895-45d7-82af-28076659d9d4', 'cloudberry'),
    ('372fe121-6c0c-4b98-a209-1a75cabb07f7', 'cloudberry'),
    ('5e640953-41e7-4094-a647-13a3782c1fc8', 'chokeberry'),
    ('243b99d0-248c-401b-be4a-5b4752d1e85d', 'chokeberry'),
    ('9c18367b-936c-4936-9cd7-9a59f34fa7a3', 'corn'),
    ('15d48fcb-978e-44cd-8ef0-b12a4380f999', 'corn'),
    ('6ba15abe-34c4-40c6-9bfc-bd503d9812a4', 'corn'),
    ('eace42ff-a615-4103-822c-365725b48d1c', 'corn tortilla'),
    ('4d59a1c8-df43-4bd5-8d6e-5bbbda084bc4', 'corn tortilla'),
    ('b1745253-61bf-4a1e-9767-214fd4ebaeb8', 'coconut'),
    ('83fb329d-d516-4f3b-8851-59f295cb13a1', 'cashew nuts'),
    ('02499482-a810-4a85-abcb-89cc6d16d57e', 'cashew nuts'),
    ('4e0031e7-7585-4fc2-ab3d-a44892e43b05', 'caraway seed'),
    ('73959493-abb4-4a4e-9e0d-77afbcd7dc56', 'caraway seed'),
    ('eaf38816-554d-47e5-8ae8-7158244c9c5f', 'cassia'),
    ('cad2747b-23f1-4252-82ee-fa4176dd1953', 'cassia'),
    ('e184ab33-4c24-4c84-aeaa-1a26a6353e0f', 'cassia'),
    ('0730e737-42c0-4706-ab88-00dad1d140a0', 'cinnamon'),
    ('fd3bdd68-9944-4d24-b2b3-fdac6337b50c', 'cinnamon'),
    ('276c65ee-bcdd-4003-818d-72e0e444bafe', 'cinnamon'),
    ('d57d102c-3773-4422-bea7-7df62e143574', 'cinnamon stick'),
    ('c12c624a-5530-4ef2-8056-dcc5c6f68cb2', 'cinnamon stick'),
    ('c64e4222-74b3-4202-8148-89dc7c8151fd', 'clove'),
    ('424d066f-fb06-4ea2-b3c4-e4c01dbc75ef', 'clove'),
    ('4364646d-84fa-43d2-aefd-dcf649ba5bed', 'chive'),
    ('2277fe96-cacf-4958-ab6b-43eff9dfd725', 'chive'),
    ('d6b76daf-83fe-4f58-abec-98cd91a04613', 'cherry tomato'),
    ('e80d70b5-89ae-4b50-8190-ce8a1ef607b5', 'cherry tomato'),
    ('e60bc0ac-0d7a-411b-b80d-86c239007107', 'cherry'),
    ('183c06d8-4013-406b-85ff-a361507aab53', 'chickpea'),
    ('4882880c-fc0d-42f2-b8d6-859372ed6880', 'chickpea'),
    ('67661bf5-88de-4b8f-b601-5b97b5e8a8a4', 'canned chickpeas'),
    ('08d17925-e841-4d86-a7ae-6481d47a05c4', 'coconut flour'),
    ('305c10be-d25a-4357-996c-c4da35c2937e', 'coconut sugar'),
    ('66ae76f2-120d-4f68-bfe4-fad79918b4af', 'Cornish hen'),
    ('df4cb485-8a16-429a-8b32-77b39f73e222', 'Cornish hen'),
    ('0c478a02-1783-473c-a2f4-76ec32736601', 'dried apricot'),
    ('5849a485-3aa0-46d9-a19e-4abfb0504673', 'dried apricot'),
    ('0e596269-2914-469b-943e-62757397669f', 'dried lime'),
    ('8bcd3150-9dd2-40b3-919e-c8d353219d14', 'dried lime'),
    ('887d505b-d0ee-45c9-b793-3708be9b8ba9', 'duck egg'),
    ('f9a1b8ef-adcb-4c5e-97f4-5bb66a33b52b', 'duck egg'),
    ('9c2aab8e-708f-462c-ae18-17d2f4773be7', 'daikon'),
    ('e2682adb-1987-4a3b-9307-cf290e790ac5', 'daikon'),
    ('2f95bbd8-3845-4f61-96fd-ad4d76aaa137', 'eggs'),
    ('3c57141a-705d-4542-95b5-a9e8f4d51b4c', 'eggs'),
    ('d547cda4-aa52-4067-947e-fea20970699d', 'egg yolk'),
    ('9d977c7c-36bd-46d0-aba7-7f3f96f27313', 'egg yolk'),
    ('b00638c9-b0cf-4edb-b37e-c149e9ae2ec4', 'egg white'),
    ('0ba93143-b0ef-4b97-92e4-b8f3a1dcf7e7', 'egg white'),
    ('96b0d487-ca87-453a-ac42-cea1be39e40e', 'elderberry'),
    ('de3661f2-255b-4555-b6aa-c8c6e421aca3', 'elderberry'),
    ('64953556-c00b-401a-b8a1-0f59fc240b2d', 'emmental'),
    ('cf943582-47b3-41e7-9e51-cc43f5a9738e', 'emmental'),
    ('143dc6e9-7bb4-4995-a75f-02c0d7ae1148', 'enoki mushroom'),
    ('6442e2ca-cb6d-438d-8493-e88cb7239c8f', 'enoki mushroom'),
    ('1e20c7cd-6eb1-4f5c-97e6-c66e09ca94ef', 'filets de maquereaux'),
    ('f0b2829e-9aff-4f95-a04f-2982163450fb', 'filets de maquereaux'),
    ('8893144a-a194-45e7-84fa-f5b3756c39da', 'filets de maquereaux'),
    ('4c9c9084-8c7b-4543-951c-8247eb3570d3', 'filets de maquereaux'),
    ('67aae911-18ca-42e3-ad9c-c3b675842f32', 'filets de maquereaux'),
    ('6d7be92f-1439-4bbd-9294-3ca11b2cd5dc', 'flour'),
    ('4f66d9bc-59f0-4ce3-b3a8-7670bfd54735', 'fingerling potato'),
    ('b564456d-5619-4c49-b37c-14c3b586ef30', 'fennel'),
    ('ad002064-a6bd-4163-b11f-140a047632c5', 'fennel'),
    ('13caecb0-16e5-4528-93c4-d8745893a4f5', 'fuyu persimmon'),
    ('507fb2e5-1cc5-4399-804b-e020b6272481', 'fuji apple'),
    ('5eaf9ded-ec92-4732-bda2-1e687b17c2ba', 'fried onions'),
    ('62f21f7d-4c57-49c1-91fe-219c28d00705', 'fried onions'),
    ('2d244347-ba62-40a7-b5db-16f7dce55b85', 'feta cheese'),
    ('c49cc46c-8374-4ed0-8b1d-372f3588403c', 'feta cheese'),
    ('7966bae4-9cf0-46d1-8d90-dd3728ddd229', 'fromage blanc'),
    ('e506f9e9-7cf5-4c6e-80dc-b4f5a8f1d759', 'fromage blanc'),
    ('a48315ff-8c9a-40ba-92f9-f18352e0cb61', 'fenugreek seeds'),
    ('20a12c17-3695-4ae8-a53f-67a24725c28b', 'fried shallots'),
    ('1abe989f-caa7-4972-9d4d-cb8888389496', 'fried shallots'),
    ('6d4ede09-92e5-477a-b5c1-e3e310928cef', 'fava beans'),
    ('e8dae424-496a-4d82-b1b7-0bf2bcc1905a', 'fava beans'),
    ('46043e37-7e48-4d08-9d51-809c1cd5f9f0', 'fermented bean curd'),
    ('325860cb-5cd6-4ab4-bb0d-7aedee1cf18e', 'fermented bean curd'),
    ('aa11cbc3-db0c-4edf-814a-af3bbe994857', 'flax seeds'),
    ('994b3003-a5dd-4b15-9cf6-7c59d606c910', 'flour tortilla'),
    ('30c51c1c-2bf0-4297-bd3b-9595a3698579', 'flour tortilla'),
    ('2c87d40b-8a70-42b2-a87a-ab027d23c461', 'fresh bay leaf'),
    ('69c134e3-720d-4f79-9a7a-adc795afc0f4', 'fresh bay leaf'),
    ('7fe8636c-807e-409c-b8c3-44ff12de33d4', 'green onion'),
    ('b1a7ed6e-72e9-4f9d-83c9-f88d4e591f95', 'green onion'),
    ('45a0b62e-e311-44ef-b6d9-de444751d82e', 'gooseberry'),
    ('4c77dbc5-5690-49c6-855d-55b130b2319f', 'gooseberry'),
    ('ed60734d-2143-4490-9aae-8fc2f57b9b4b', 'goji berry'),
    ('eff3eaf9-819a-49a1-8768-d02963782cf0', 'goji berry'),
    ('87af4a99-ac8b-49f7-80fe-1be2fe622d66', 'green bean'),
    ('5b8a04af-943e-44ce-a502-f98d3690fe40', 'green bean'),
    ('914cf325-f66d-48cd-a4a2-4637bd488812', 'goat cheese'),
    ('644e7a45-3c5e-428a-9a86-56ccf2c57ca0', 'goat cheese'),
    ('a59450ee-e7de-4de7-96ba-f0f4fd8ae4a2', 'garlic chives'),
    ('294c937f-d1fd-4c22-aa8c-4f2f3b00fad6', 'garlic chives'),
    ('300b00cc-a651-4e69-b706-78cf9968f1b3', 'grape'),
    ('aac3c7c0-5780-4f60-8123-d85f8ad16632', 'grape'),
    ('1d4c1fcb-364c-4ec9-8f32-ba22e4451d4b', 'guajillo chili'),
    ('d8e019fa-0e6e-43d1-ada9-c0150c86775c', 'guajillo chili'),
    ('b82f8c4f-9e8c-40a8-bfc0-29ba952b3e8f', 'huckleberry'),
    ('c58c61ba-509d-4b35-bf21-d1e9d231b47d', 'huckleberry'),
    ('681e9686-b2bf-4773-b092-a7ad81f2acb8', 'halloumi'),
    ('5e41c734-4252-4c5e-9511-057ffd674ce9', 'halloumi'),
    ('6b550388-0da5-47b8-af06-88b75f96dcbf', 'harissa'),
    ('a6f484d1-a7ce-4a3b-85c1-4a8090477708', 'harissa'),
    ('2f17a864-ec98-4838-bf21-66ef33c1524d', 'harissa powder'),
    ('62bfeb50-fbcb-47f2-aec3-b2baf603de26', 'harissa powder'),
    ('8f3285bc-384c-4cb7-91a0-96e42b5513b1', 'habanero'),
    ('dc8cf0ec-fb27-4878-8288-ec9c40371d2c', 'habanero'),
    ('87e9c47b-5abc-44d7-b652-8921f3fedeb2', 'haricots verts'),
    ('8809976e-4bde-4ded-b74f-caf6ee249e71', 'haricots verts'),
    ('c673ae1a-64a2-4f15-85d4-c0eebb23a867', 'Idiazabal cheese'),
    ('8691687b-57ed-4001-9aaf-9c1a4863a7c5', 'Idiazabal cheese'),
    ('d3bf2471-55a1-41fc-87e4-84e6ef5b2da0', 'invert sugar syrup'),
    ('d128a3e2-7f64-463b-a222-c746042f62cf', 'invert sugar syrup'),
    ('aa755c80-8ad5-43de-a70d-3aba7bcaa6c4', 'iceberg lettuce'),
    ('c74c9888-2046-4c35-830c-45025e9989b0', 'iceberg lettuce'),
    ('bba16614-2299-4a9b-b1db-f93468f71913', 'italian chopped tomatoes in tomato juice'),
    ('58cbbc5f-a098-456e-a9bc-8db1a99a5001', 'italian chopped tomatoes in tomato juice'),
    ('74501917-ab82-4178-ae15-48cd0ddde4fa', 'jalapeño pepper'),
    ('ffd0a5f6-604a-48aa-a866-255bb0293e38', 'jalapeño pepper'),
    ('1bb2e3c0-6a03-4aa9-bb6b-1e2159260f48', 'jalapeño pepper'),
    ('6d486bbd-8f5c-43d1-b708-6a841875a84b', 'Japanese short-grain rice'),
    ('bf827aac-8c13-455d-9943-2e0d613be9aa', 'Japanese short-grain rice'),
    ('a0530cc9-683a-47df-a272-fff3e3b5972d', 'jollof rice'),
    ('da7a01c0-f9e1-463f-8ebd-8e7ac2f92c4d', 'jollof rice'),
    ('4ec2c240-1a6a-405a-a069-6678ad114ccc', 'kiwi'),
    ('2949e9a9-6f3d-4ac3-beee-7ffcd26e49c0', 'kiwi'),
    ('82e031b8-7583-4cbb-990c-4ebbad483480', 'kola nut'),
    ('c18ead82-90e7-4468-872d-e262d9343c77', 'kola nut'),
    ('21c15c4a-d150-492a-93cb-d3b514f3c675', 'kombu'),
    ('a7de8176-cf56-48fa-8efb-4deaf9d17c2f', 'kombu'),
    ('4ac5d22b-b9f5-4235-a0d6-0114483f0e47', 'king oyster mushroom'),
    ('8e5af42b-46db-4d7c-874c-c3c202a1f9a5', 'king oyster mushroom'),
    ('3e005927-202c-4fca-98e8-1fceae0ff0af', 'kashk'),
    ('9f28c59c-c5e7-449e-a875-18e23817eba7', 'kashk'),
    ('1b5359ce-d243-42b5-bdc3-cffd4531d156', 'lemon'),
    ('8e3a6569-6332-495b-b68e-1bed47ec5147', 'lemon'),
    ('aa3c7453-23cf-4300-9c85-89eaf6902d45', 'lime'),
    ('1638a96e-5363-48ce-b6b2-f432c8c26f7e', 'lime'),
    ('b52417a9-afe5-4042-91a1-ad716174f78b', 'loganberry'),
    ('64a73d04-0ef3-4f5c-937f-74b2aac6a46f', 'loganberry'),
    ('5523a94e-0b17-4bd4-97df-6afc52e1d13b', 'lingonberry'),
    ('dc9214a0-e71c-4cfd-b2e0-d84ed7f40690', 'lingonberry'),
    ('777d4b2d-3af8-4a28-92d6-9603a2ea044a', 'long bean'),
    ('6598eb56-294e-435e-b16b-1eee9fec4c80', 'long bean'),
    ('a27988d3-13ab-4cfb-8821-f89b60323e0e', 'luffa'),
    ('8dc2f83a-20d4-4d38-af3c-7a9c49b44070', 'luffa'),
    ('c2e85ad4-7dda-42b3-91c0-bb438b52cc20', 'leek'),
    ('585ff1d2-38fa-47b4-9fa1-8854095ff457', 'leek'),
    ('f35f4843-350d-4df8-b55a-6c1c8a669e3d', 'liquid egg'),
    ('f6dff3e3-4d17-42d8-975a-1cde55dfd9d7', 'liquid egg'),
    ('dc26d5ec-3e80-4eb6-86c6-cb3ce55118e0', 'lamb chop'),
    ('eca9788f-b5f3-4319-b7ca-68a60cd625c1', 'lamb chop'),
    ('bd25d3d3-86a9-4559-b7fc-61d81c5356ea', 'marionberry'),
    ('a2dcf410-ea8f-43c2-8af1-7f33ea96b16a', 'marionberry'),
    ('be88c824-7a80-4ddc-9c65-2eebdef5030c', 'mulberry'),
    ('cac4ccfd-2986-452f-a7e3-2c57c555de7b', 'mulberry'),
    ('a42dc515-a19e-44f4-ac8c-519d7dd95c38', 'maqui berry'),
    ('0b3cf9d2-063b-4df2-b13f-99e3b717c452', 'maqui berry'),
    ('76638e8d-1157-4b37-bcde-ee09d1f0669e', 'malabar chestnut'),
    ('b03b346e-f552-4ca3-a608-85d32700bb7c', 'malabar chestnut'),
    ('0f799c3a-2909-4b3b-8156-0f571fd9c93e', 'malabar spinach'),
    ('fee6e3c8-0f2a-495d-b1d7-c824e720a5a7', 'malabar spinach'),
    ('7f2c3f68-944a-4f08-9d91-e883c23e0e14', 'macadamia nut oil'),
    ('8c71782d-28ec-40a7-b671-b2d21925ff72', 'macadamia nut oil'),
    ('e0c5da66-93e7-4555-ae8e-31384a2281e7', 'macadamia nut butter'),
    ('6f65f7ff-1cc4-40c1-aedc-0b64eaeccbc5', 'mee kia'),
    ('1b619c68-94db-4e87-a4f1-38154c3cdb4d', 'mee kia'),
    ('f1eb9be9-0b30-4f89-8974-fe15fbe6e3db', 'mee pok'),
    ('038c417e-e48c-4deb-8d05-40cd688fde0d', 'mee pok'),
    ('59a1a600-d2e7-4741-a40f-8427999f5ea7', 'mizithra cheese'),
    ('4b77a278-3091-479c-a65a-fe597df91884', 'mizithra cheese'),
    ('b690583c-ef11-4fa1-b376-ef1c1bc1cd8f', 'mahlab'),
    ('0156a1d9-8652-4097-a6ed-c45d95409a31', 'mahlab'),
    ('d559dce0-e707-491e-b7d2-9bc6a6a83f52', 'miracle fruit'),
    ('17731f72-37df-41f5-8f1d-f3dd8cf1edad', 'miracle fruit'),
    ('75c83d64-7760-4b11-a9c5-043a4601c179', 'miracle fruit'),
    ('a05eddea-d82e-4ddf-8383-ca9636971170', 'mustard powder'),
    ('bdd634da-7af2-4a41-b123-602f21fe7aae', 'mustard powder'),
    ('f9689b6e-6caa-4369-82a2-42a071c17d1e', 'mustard spinach'),
    ('0bc1afa8-db2d-407a-858c-bb5c69711701', 'mustard spinach'),
    ('916750be-5ee5-4787-bc9d-3d4c1389b92d', 'mushroom'),
    ('2516d30b-2712-4a7a-85ec-07b67d1be101', 'mushroom'),
    ('49178536-0dbc-4f6b-8e95-ae9b5111a6be', 'marrowfat peas'),
    ('bc12c93a-2d64-4607-acd1-baff961ead69', 'marrowfat peas'),
    ('d58c7673-9316-4c7a-8f90-bdcc1036324b', 'mustard seeds'),
    ('166a5d3d-a627-4133-a6fc-494799aa93f0', 'manchego'),
    ('493a5a3b-1173-44e4-86ca-720513bddc7a', 'manchego'),
    ('3137fbc1-e9c4-4c33-86bc-139610bae12c', 'mung dal'),
    ('3dfd57b5-c26d-4028-a1e5-f58df8e19bdc', 'mung dal'),
    ('2d9047d4-a870-4b1b-ba11-8984aac5b0fb', 'new potato'),
    ('f4cd4412-9f77-4a99-8f0a-2043a4519cf7', 'navel orange'),
    ('43b48548-c3bd-40e7-a7cd-daf0b9e3de6c', 'nectarine'),
    ('0e0892c5-880a-4ca8-b9e7-1eb9f1b69e6a', 'onion'),
    ('5b53a769-589a-43b9-968f-d792a07611d7', 'onion'),
    ('bd306bef-cc19-4d55-85ca-8a370643e2f5', 'olive'),
    ('3c783b81-f292-4745-9185-854915c06f1a', 'olive'),
    ('53b448c2-d448-49ab-abc3-2eea87296f96', 'Old Bay'),
    ('bba95888-7004-4d5c-aa99-b64ae11cb16f', 'Old Bay'),
    ('1c0ad1ac-99c2-4ea9-8e3c-c03705a8b990', 'ostrich egg'),
    ('a8b74bee-63f6-4690-ab8e-7b7b68ee8dd9', 'ostrich egg'),
    ('0f85463c-6cf8-4f92-8e8c-bd5730040cdd', 'quail egg'),
    ('0b3eb7c5-9318-40b5-ab3c-81db93dfeafc', 'quail egg'),
    ('d36a6334-6d4b-4f89-99c8-8ed7048b6c2e', 'quail whole'),
    ('78763c52-ac39-4611-9870-4c3954b28a0f', 'quail whole'),
    ('8adb93b1-33a2-4d8b-8619-d13924cad9b3', 'romaine lettuce'),
    ('e48f346c-4871-43ef-8ad8-f98bf3bdaa4f', 'ramps'),
    ('a95c22b9-0961-4d6e-8cc2-95c8687183e7', 'ramps'),
    ('e66aa64b-ed1e-453f-8673-49f3467aba9b', 'rainbow chard'),
    ('bcae3123-f5f6-4f14-8f49-d736edd7c244', 'rainbow chard'),
    ('c799bb54-77fb-40d3-92b5-c6d37b85e300', 'raspberry'),
    ('d58a390d-f319-4bdb-a175-7604e2503fb8', 'raspberry'),
    ('07b161ef-e788-4fca-a54f-80f6fc247a80', 'rowan berry'),
    ('42bdf473-0c52-491a-adcd-48f9c3bf99b0', 'rowan berry'),
    ('068ca4a7-3de1-4e5c-a071-8af0a8bed4bb', 'rowan berry'),
    ('0f9eca0f-b88f-4526-bd97-24912c9ba0e6', 'red onion'),
    ('3e71c347-e580-49a3-aa36-6aca507a65ad', 'red onion'),
    ('ecf01923-2c84-4e8d-b20c-9474cc6b179a', 'rose water'),
    ('8f82add4-6697-45d3-815a-fc30577613ac', 'rose water'),
    ('cc03eb07-da41-49f6-98be-b273de082baa', 'razor clam'),
    ('60a45869-7a28-4b73-8610-c7f6f25efcd2', 'razor clam'),
    ('da918af1-a540-44f6-8dd7-b2773da6188b', 'romanesco'),
    ('8dbc3d38-cd49-4c99-aaf2-412050d1430b', 'romanesco'),
    ('352f8c21-34d7-4437-a31b-e802d92bb870', 'strawberry'),
    ('7c680949-381a-4a1c-a2e0-13e25b30dfa9', 'strawberry'),
    ('51250bc5-49a8-4580-b260-b82024175768', 'sun-dried tomato'),
    ('6b19b773-cdc8-4239-ad23-55614e3768d6', 'sun-dried tomato'),
    ('7ef6255b-a764-4097-a251-6c10ecaaad70', 'scallion'),
    ('664295b6-22e9-4368-bf30-4a7de90ceab7', 'scallion'),
    ('6ba09fc5-c9cb-43db-bea4-8fd6ce7bb7af', 'snap pea'),
    ('61f639d9-d635-4906-a31c-8ee8bb0c04ed', 'snap pea'),
    ('560c810c-e7ab-4119-b6bf-40016e6c269f', 'snap pea'),
    ('acc0b49e-c42b-442f-8a55-0463889ce933', 'snow pea'),
    ('67b6ae3f-20b5-4205-a2f8-b87307788023', 'snow pea'),
    ('2bfd76bf-2af2-4a3c-bd77-b06d0a4ed2dd', 'serviceberry'),
    ('5dc9368d-2d8f-4923-a567-da399540d16e', 'serviceberry'),
    ('0186c003-095c-4b51-8eb1-57b13f7c0441', 'salmonberry'),
    ('d88d1c2c-1f86-435c-9b48-52eb87e893a4', 'salmonberry'),
    ('e8aef642-447c-4ab4-ac92-0607a483e53e', 'shiso'),
    ('3d7caee5-da76-4dd7-95d1-86a68e9b0771', 'shiso'),
    ('a937799a-6d7f-4a9b-b357-fd15c7d8c847', 'shiso'),
    ('779adcd0-d360-411b-86ec-e0c7b3b7bd5c', 'shiitake mushroom'),
    ('576a61bf-25b8-4311-9d38-af54644cf4b1', 'shiitake mushroom'),
    ('59bc9fad-1609-4d82-885e-75793fc52886', 'shimeji mushroom'),
    ('8b2a013b-d8d8-485d-bf27-ce8496229892', 'shimeji mushroom'),
    ('b0c9034c-da37-4d4f-ac06-a712cfa19893', 'scotch bonnet pepper'),
    ('739e02a4-a88a-45a5-89bb-b2a306f8c109', 'scotch bonnet pepper'),
    ('a863e80d-4bac-472d-bc62-2efdc9afa457', 'shallot'),
    ('d737188e-47ad-4add-be06-593f7348c8d1', 'sofrito'),
    ('8dc32d66-da9f-4a11-a1f4-a4825a17350e', 'sofrito'),
    ('bf3e3a2f-3647-4e20-bfdb-24a8d408563f', 'sofrito'),
    ('f44eb200-ac4a-420c-9ebc-9ff757a5efce', 'sardine'),
    ('df1ea10d-c173-4738-a091-43586c9b2db5', 'sardine'),
    ('bbcad5e9-72e4-4c8a-bb2b-950ba67db0be', 'sea buckthorn berry'),
    ('64356a40-4379-4b13-8c2f-dd00dbc620e5', 'sea buckthorn berry'),
    ('5b119d5e-cc66-46c5-b44d-a6eef5cdc4c3', 'star fruit'),
    ('e5342c14-e34c-4949-8df2-50498a6a6d75', 'star fruit'),
    ('f4587725-0a4e-457c-b1b9-8cb07e650730', 'salted duck egg'),
    ('2828321c-4a53-4df8-8818-dd7c03d9b924', 'salted duck egg'),
    ('b574c39b-0fe6-46b5-a279-3f712d1e8fcd', 'sumac'),
    ('d7514dd8-37d4-457e-872a-9d9036f42448', 'sumac'),
    ('a6eb985d-b48b-4d50-9c2a-a2f2713f3c0f', 'saffron'),
    ('aa6ffe6b-493a-4e4a-af3d-2fe0717acae6', 'saffron'),
    ('96de4948-7eab-4316-b827-9c1b3ce15172', 'sazon'),
    ('0191611b-0abe-4a32-9a30-bd137b520e0c', 'sazon'),
    ('a17b6dfb-410d-4534-9689-9248113c3ff5', 'shawarma seasoning'),
    ('ff8a3bee-2a76-487b-a536-f105899a8f5f', 'shawarma seasoning'),
    ('b6d8ba3f-de23-438c-82c9-a6bbf0155a06', 'shawarma seasoning'),
    ('db8ba22a-15ce-4c87-8e36-2b260e950a7e', 'shawarma seasoning'),
    ('ce166f4e-5db7-4006-9fef-08eef372f532', 'semolina'),
    ('c727c0d6-0622-47ed-9378-23cd8435d274', 'semolina'),
    ('3009aca6-5e45-4822-8281-a5bc81b5ff3e', 'somen noodles'),
    ('1f8c6a49-ff67-4a85-a2c6-7831295af23e', 'somen noodles'),
    ('928316db-01f9-4d61-8bd8-a0a56cf55c96', 'scallop'),
    ('e3231c2a-b591-4d21-9ae1-9034fd30b014', 'scallop'),
    ('5e188f0b-a676-4ef1-8b49-3e7c572e25ee', 'sacha inchi'),
    ('96f0fff2-9815-4c7b-a6ee-29ff50e7f721', 'sacha inchi'),
    ('a716ad20-0870-46b0-a248-ec147a12d483', 'salt cod'),
    ('4ae0f1ec-3344-41c3-85ba-c3eb07d3c1e1', 'salt cod'),
    ('91867f94-ed92-47aa-8a49-f31483bd4e3c', 'sour orange'),
    ('f1ba3a09-8447-4d8c-be30-5d167ea721dc', 'sour orange'),
    ('cb63ea7f-06a8-4845-8758-e920b3139fc8', 'skyr'),
    ('eddb22e3-4c2b-4023-aad3-8379b815c3a0', 'skyr'),
    ('969caafe-7c71-4723-acff-de0c94751c8f', 'short grain rice'),
    ('e4b46b93-2391-410b-b165-821044a9e69b', 'short grain rice'),
    ('eb748a7a-e4c0-429a-9705-4651073af7fe', 'taleggio'),
    ('ed6015ee-b92f-42fa-9096-b450447e83bf', 'taleggio'),
    ('43f9cae4-c3ac-491b-aaeb-dcc8742f51ae', 'turkey egg'),
    ('bdaf3ea8-d79a-499e-b110-040706d8dfc0', 'turkey egg'),
    ('0e63720f-786c-4f2d-8752-99a3fee35158', 'turnip'),
    ('0f2a44bc-5c4f-43bc-b29e-03dee52005eb', 'turnip'),
    ('94edb096-8010-40e2-bc2d-ee75533a0a50', 'tayberry'),
    ('cf38c977-6bcc-4506-bd39-91f9e5abd606', 'tayberry'),
    ('68bf64d6-2911-4bb5-b432-4ae0da93901f', 'tapioca flour'),
    ('ab6bc122-a3ad-4289-941e-505c0acea13e', 'tapioca flour'),
    ('27292627-bf7c-4fe9-a7c4-b9ec5003a063', 'turmeric root'),
    ('e7d687e0-ceff-47d8-9659-9c1466d15a89', 'turmeric root'),
    ('55d07bdc-c25a-4ea9-91cb-f018e79f33ed', 'turmeric'),
    ('83c83197-1a2e-48e9-b0ee-605dfa71af33', 'turmeric'),
    ('49068e8f-5577-42e0-81eb-c2d8373f9a67', 'taro'),
    ('dfb4159f-2627-48c4-b7db-d929fa4cb845', 'taro'),
    ('8033c840-6c65-458e-b31f-0a023ea891b0', 'tomato'),
    ('b76a06a5-4f15-4b1d-8510-252096026d37', 'tomato'),
    ('b26346ea-5ff0-45a6-9aab-e61ed8895147', 'turkey sausage'),
    ('ca80d03c-2072-4352-85a4-c9d68d83ffcb', 'thai chili'),
    ('933af903-6f84-46f5-9b2a-7127e784230b', 'thai chili'),
    ('40d58238-4d90-4155-b534-55d54ed08999', 'thai chili'),
    ('42c076ca-9325-429b-80eb-941ebf15668c', 'triple cream cheese'),
    ('d814a316-69c0-4d0d-92f9-c54177ed032a', 'triple cream cheese'),
    ('bba9e196-971e-4713-b5cb-1ae893b6cd83', 'tiger nut'),
    ('787e753c-88f9-4b9c-8c5b-0f34c21a231a', 'tiger nut'),
    ('6716be78-fdf7-40af-a4c0-6390bb479b59', 'udon noodles'),
    ('793792ed-c4a2-4cde-b504-cbef8cc90ef4', 'udon noodles'),
    ('c1bb09df-e291-4a9f-9530-798b2f06f634', 'ugu leaf'),
    ('34be42fd-1b1f-48b3-9698-2ca7d0d9e339', 'ugu leaf'),
    ('ff6fc3d7-dc1c-4b05-95f9-b52543843a30', 'venison tenderloin'),
    ('df3ba132-703c-4d85-85d9-585ed89c0b7f', 'venison tenderloin'),
    ('6fbd4173-cda9-4dff-b0e8-c671b90ce051', 'wineberry'),
    ('75e15cdf-e900-4f21-a7e8-0199caf7ef84', 'wineberry'),
    ('b0336292-4846-4089-9205-bf356d420e49', 'wax bean'),
    ('86a57fb7-b8e0-4ab0-b4f2-ed496059f123', 'wax bean'),
    ('f5dadced-8fc5-4091-afec-ef55bd0dc1eb', 'water chestnut'),
    ('ef651260-ad70-46db-a31c-7508e8cbef9a', 'water chestnut'),
    ('e9897c0d-f762-4afa-8aa7-756243e5127f', 'wood ear mushroom'),
    ('3813b488-c02b-4126-92a4-616996a42013', 'wood ear mushroom'),
    ('fbbec10d-d148-4972-ad0f-b74cb939abb9', 'Yukon Gold potato'),
    ('57fb08aa-a18e-4a40-9e9e-0e961af8a52d', 'yam'),
    ('048bdf5b-e6c1-4a22-83f1-af5561c30f79', 'yam'),
    ('3f302291-f91b-4539-b853-467a62ec0eb2', 'yellow tomato'),
    ('7355d855-e515-44be-9ad7-8bfe5541368a', 'yardlong bean'),
    ('0b063544-6618-42cb-9e8a-260121f19a0d', 'yardlong bean'),
    ('42a69120-aaf8-4d35-be76-99bcc83b226d', 'yellow lentils'),
    ('ddbd7e08-7f77-47da-ba9d-223d960c2ef4', 'yellow lentils'),
    ('04078412-72e3-42f1-9aad-893561120ab5', 'yellow mustard seeds'),
    ('cf5f3b19-6b7d-4f65-b42d-3fc581617fe1', 'zopf bread'),
    ('77931ced-0f2a-4de7-af3e-1b8d2876ab40', 'zucchini');

ALTER TABLE dedupe_map ADD COLUMN canonical_id UUID;

-- Resolve canonical IDs by name.
-- The LLM often included the canonical's own ID in the merge list,
-- so we match by name WITHOUT excluding merge IDs.
-- If multiple ingredients share the same name, pick the one in our merge list
-- (it will be removed from deletion later).
UPDATE dedupe_map dm
SET canonical_id = sub.resolved_id
FROM (
    SELECT DISTINCT ON (LOWER(canonical_name)) canonical_name,
        i.id AS resolved_id
    FROM dedupe_map dm2
    JOIN ingredients i ON LOWER(i.name) = LOWER(dm2.canonical_name)
    ORDER BY LOWER(canonical_name), i.id
) sub
WHERE LOWER(dm.canonical_name) = LOWER(sub.canonical_name);

-- Fallback: try unaccented/trimmed match for diacritics (e.g. açaí vs acai)
-- Only if the unaccent extension is available
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'unaccent') THEN
        EXECUTE '
            UPDATE dedupe_map dm
            SET canonical_id = sub.resolved_id
            FROM (
                SELECT DISTINCT ON (unaccent(LOWER(canonical_name))) canonical_name,
                    i.id AS resolved_id
                FROM dedupe_map dm2
                JOIN ingredients i ON unaccent(LOWER(TRIM(i.name))) = unaccent(LOWER(TRIM(dm2.canonical_name)))
                WHERE dm2.canonical_id IS NULL
                ORDER BY unaccent(LOWER(canonical_name)), i.id
            ) sub
            WHERE LOWER(dm.canonical_name) = LOWER(sub.canonical_name)
              AND dm.canonical_id IS NULL;
        ';
    END IF;
END $$;

-- Fallback: for groups where no ingredient matches the canonical name at all,
-- pick the first merge_id as the canonical (keep it, delete the rest).
-- This handles cases where the LLM chose a normalized name that doesn't
-- exist verbatim in the DB (e.g. "filets de maquereaux", "sacha inchi").
UPDATE dedupe_map dm
SET canonical_id = sub.first_id
FROM (
    SELECT DISTINCT ON (canonical_name) canonical_name, duplicate_id AS first_id
    FROM dedupe_map
    WHERE canonical_id IS NULL
    ORDER BY canonical_name, duplicate_id::text
) sub
WHERE dm.canonical_name = sub.canonical_name
  AND dm.canonical_id IS NULL;

-- Remove entries where duplicate_id IS the canonical (don't delete the canonical itself)
DELETE FROM dedupe_map WHERE duplicate_id = canonical_id;

-- Abort if any canonical name couldn't be resolved
DO $$
DECLARE
    unresolved INT;
    examples TEXT;
BEGIN
    SELECT COUNT(DISTINCT canonical_name),
           string_agg(DISTINCT canonical_name, ', ' ORDER BY canonical_name)
    INTO unresolved, examples
    FROM dedupe_map WHERE canonical_id IS NULL;

    IF unresolved > 0 THEN
        RAISE EXCEPTION 'Dedupe aborted: % unresolved canonicals: %', unresolved, examples;
    END IF;
END $$;

-- ============================================================
-- Step 1: Remap FK references from duplicates to canonicals
-- ============================================================

UPDATE inventory SET ingredient_id = dm.canonical_id
FROM dedupe_map dm WHERE inventory.ingredient_id = dm.duplicate_id;

UPDATE recipe_ingredients SET ingredient_id = dm.canonical_id
FROM dedupe_map dm WHERE recipe_ingredients.ingredient_id = dm.duplicate_id;

UPDATE shopping_list SET ingredient_id = dm.canonical_id
FROM dedupe_map dm WHERE shopping_list.ingredient_id = dm.duplicate_id;

UPDATE flavor_preferences SET ingredient_id = dm.canonical_id
FROM dedupe_map dm WHERE flavor_preferences.ingredient_id = dm.duplicate_id;

-- Remove inventory duplicates created by remapping
-- (user had both canonical and duplicate in inventory)
DELETE FROM inventory WHERE id IN (
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY user_id, ingredient_id
            ORDER BY updated_at DESC, created_at DESC, id DESC
        ) AS rn FROM inventory WHERE ingredient_id IS NOT NULL
    ) ranked WHERE rn > 1
);

-- Remove flavor_preferences duplicates created by remapping
DELETE FROM flavor_preferences WHERE id IN (
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY user_id, ingredient_id
            ORDER BY updated_at DESC, id DESC
        ) AS rn FROM flavor_preferences WHERE ingredient_id IS NOT NULL
    ) ranked WHERE rn > 1
);

-- ============================================================
-- Step 2: Remap assumed_staples UUID arrays in preferences
-- ============================================================

UPDATE preferences p
SET assumed_staples = (
    SELECT ARRAY(
        SELECT DISTINCT COALESCE(dm.canonical_id, elem)
        FROM unnest(p.assumed_staples) AS elem
        LEFT JOIN dedupe_map dm ON dm.duplicate_id = elem
    )
)
WHERE p.assumed_staples && ARRAY(SELECT duplicate_id FROM dedupe_map);

-- ============================================================
-- Step 3: Merge aliases + names from duplicates into canonicals
-- ============================================================

WITH merged_aliases AS (
    SELECT
        dm.canonical_id,
        ARRAY(
            SELECT DISTINCT val FROM (
                -- Existing canonical aliases
                SELECT unnest(COALESCE(canonical.aliases, '{}')) AS val
                UNION
                -- Duplicate names (become aliases)
                SELECT dup.name AS val
                FROM dedupe_map dm2
                JOIN ingredients dup ON dup.id = dm2.duplicate_id
                WHERE dm2.canonical_id = dm.canonical_id
                UNION
                -- Duplicate aliases
                SELECT unnest(COALESCE(dup.aliases, '{}')) AS val
                FROM dedupe_map dm2
                JOIN ingredients dup ON dup.id = dm2.duplicate_id
                WHERE dm2.canonical_id = dm.canonical_id
            ) all_aliases
            WHERE val IS NOT NULL
              AND LOWER(val) != LOWER(canonical.name)
        ) AS new_aliases
    FROM (SELECT DISTINCT canonical_id FROM dedupe_map) dm
    JOIN ingredients canonical ON canonical.id = dm.canonical_id
)
UPDATE ingredients i
SET aliases = ma.new_aliases
FROM merged_aliases ma
WHERE i.id = ma.canonical_id;

-- ============================================================
-- Step 4: Delete duplicate ingredient rows
-- ============================================================

DELETE FROM ingredients WHERE id IN (SELECT duplicate_id FROM dedupe_map);

-- Cleanup
DROP TABLE dedupe_map;

COMMIT;
