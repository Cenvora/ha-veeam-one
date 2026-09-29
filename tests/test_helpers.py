from custom_components.veeam_one.coordinator import as_dict, items

class Model:
    def to_dict(self):
        return {"items":[{"name":"Job"}],"totalCount":1}

def test_as_dict():
    assert as_dict(Model())["totalCount"] == 1

def test_items():
    assert items(Model()) == [{"name":"Job"}]
