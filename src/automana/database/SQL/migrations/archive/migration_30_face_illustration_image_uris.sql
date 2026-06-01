-- Backfill illustrations.image_uris for face illustrations.
--
-- The insert_full_card_version procedure was not storing image_uris when
-- inserting face illustration rows.  For DFC cards (face_index > 0) the back
-- face URL follows the same Scryfall CDN pattern as the front face but with
-- '/back/' instead of '/front/'.  For front faces (face_index = 0) the image
-- is already stored in card_version_illustration, so we copy it there too.

UPDATE card_catalog.illustrations il
SET    image_uris  = face_img.image_uris,
       updated_at  = now()
FROM (
    -- face_index 0: copy image_uris directly from card_version_illustration
    SELECT fi.illustration_id,
           cvi.image_uris
    FROM   card_catalog.face_illustration fi
    JOIN   card_catalog.card_faces        cf  ON cf.card_faces_id  = fi.face_id
    JOIN   card_catalog.card_version_illustration cvi
                                              ON cvi.card_version_id = cf.card_version_id
    WHERE  cf.face_index = 0
      AND  cvi.image_uris IS NOT NULL

    UNION ALL

    -- face_index > 0 (back/transform faces): derive from front URL by swapping /front/ -> /back/
    SELECT fi.illustration_id,
           jsonb_build_object(
               'small',    replace(cvi.image_uris->>'small',    '/front/', '/back/'),
               'normal',   replace(cvi.image_uris->>'normal',   '/front/', '/back/'),
               'large',    replace(cvi.image_uris->>'large',    '/front/', '/back/'),
               'png',      replace(cvi.image_uris->>'png',      '/front/', '/back/'),
               'art_crop', replace(cvi.image_uris->>'art_crop', '/front/', '/back/'),
               'border_crop', replace(cvi.image_uris->>'border_crop', '/front/', '/back/')
           ) AS image_uris
    FROM   card_catalog.face_illustration fi
    JOIN   card_catalog.card_faces        cf  ON cf.card_faces_id  = fi.face_id
    JOIN   card_catalog.card_version      cv  ON cv.card_version_id = cf.card_version_id
    JOIN   card_catalog.card_version_illustration cvi
                                              ON cvi.card_version_id = cf.card_version_id
    WHERE  cf.face_index > 0
      AND  cv.is_multifaced = TRUE
      AND  cvi.image_uris IS NOT NULL
      AND  cvi.image_uris->>'large' LIKE '%/front/%'
) face_img
WHERE il.illustration_id = face_img.illustration_id
  AND il.image_uris IS DISTINCT FROM face_img.image_uris;
