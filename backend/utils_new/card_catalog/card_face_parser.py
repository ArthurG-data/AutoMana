def parse_card_faces(raw_faces_list: list[dict]):
    card_faces = []
    for i in range(len(raw_faces_list)):
        face_data = raw_faces_list[i]
        face_data["face_index"] = i
        card_faces.append(face_data)
    return card_faces