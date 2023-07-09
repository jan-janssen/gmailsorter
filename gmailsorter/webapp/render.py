def color_for_status(status):
    if status == "success":
        return '<span style="color:MediumSeaGreen;">' + status + "</span>"
    elif status == "failed":
        return '<span style="color:Tomato;">' + status + "</span>"
    else:
        return '<span style="color:Orange;">' + status + "</span>"
