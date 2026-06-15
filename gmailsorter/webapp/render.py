from gmailsorter.daemon.shared import JOB_STATUS_FAIL, JOB_STATUS_SUCCESS


def color_for_status(status):
    if status == JOB_STATUS_SUCCESS:
        return '<span style="color:MediumSeaGreen;">' + status + "</span>"
    elif status == JOB_STATUS_FAIL:
        return '<span style="color:Tomato;">' + status + "</span>"
    else:
        return '<span style="color:Orange;">' + status + "</span>"
