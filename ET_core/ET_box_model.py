# ET_core/ET_box_model.py

from dataclasses import dataclass, asdict
import uuid


@dataclass
class TrimBox:
    id: str
    name: str

    u_min: float
    v_min: float
    u_max: float
    v_max: float

    color: tuple = (1.0, 0.82, 0.1, 1.0)
    padding_px: int = 4
    fit_mode: str = "fit_height"
    repeat_u: bool = False
    repeat_v: bool = False
    locked: bool = False
    z_index: int = -200

    @staticmethod
    def create(
        name="Trim Box",
        u_min=0.25,
        v_min=0.25,
        u_max=0.75,
        v_max=0.75,
        z_index=-200
    ):
        return TrimBox(
            id="box_" + uuid.uuid4().hex[:8],
            name=name,
            u_min=u_min,
            v_min=v_min,
            u_max=u_max,
            v_max=v_max,
            z_index=z_index
        )

    def to_dict(self):
        return asdict(self)


class ETrimModel:
    """
    Source of truth for eTrim.

    Qt widgets never own the real data.
    The viewer only displays this model.
    """

    def __init__(self):
        self.version = 1
        self.texture_path = ""
        self.texture_resolution = [2048, 2048]

        self.boxes_by_id = {}
        self.box_order = []
        self.active_box_id = None

    # -----------------------------------------------------
    # Box management
    # -----------------------------------------------------
    def get_next_box_z_index(self):
        """
        Boxes start deep below UVs and advance upward by 2.
        |First box | Second box | Third box |
        |   -200   |    -198    |   -196    |
        """

        return -200 + (len(self.box_order) * 2)
    def rects_overlap(self, a_u_min, a_v_min, a_u_max, a_v_max,
                    b_u_min, b_v_min, b_u_max, b_v_max):
        """
        Return True if two boxes overlap with actual area.

        Touching edges is allowed.
        """

        if a_u_max <= b_u_min:
            return False

        if a_u_min >= b_u_max:
            return False

        if a_v_max <= b_v_min:
            return False

        if a_v_min >= b_v_max:
            return False

        return True


    def box_area_is_free(self, u_min, v_min, u_max, v_max):
        """
        Check whether a proposed box area overlaps existing boxes.
        """

        for box in self.iter_boxes():
            if self.rects_overlap(
                u_min,
                v_min,
                u_max,
                v_max,
                box.u_min,
                box.v_min,
                box.u_max,
                box.v_max
            ):
                return False

        return True


    def find_free_box_rect(self):
        """
        Find the first available non-overlapping place for a new trim box.

        Searches the 0-1 tile from top-left to bottom-right.

        Returns:
            (u_min, v_min, u_max, v_max)
        """

        # Try nice practical default sizes first.
        candidate_sizes = [
            (0.25, 0.25),
            (0.20, 0.20),
            (0.125, 0.125),
            (0.10, 0.10),
            (0.05, 0.05)
        ]

        step = 0.025

        for width, height in candidate_sizes:
            # Search visually from top to bottom.
            v = 1.0 - height

            while v >= -0.0001:
                u = 0.0

                while u + width <= 1.0001:
                    u_min = round(u, 5)
                    v_min = round(v, 5)
                    u_max = round(u + width, 5)
                    v_max = round(v + height, 5)

                    if self.box_area_is_free(
                        u_min,
                        v_min,
                        u_max,
                        v_max
                    ):
                        return u_min, v_min, u_max, v_max

                    u += step

                v -= step

        # If everything is full, return a tiny fallback in the corner.
        # In practice we will later warn the user instead.
        return 0.0, 0.0, 0.05, 0.05

    def create_box(self):
        index = len(self.box_order) + 1

        u_min, v_min, u_max, v_max = self.find_free_box_rect()

        box = TrimBox.create(
            name="Trim Box {:02d}".format(index),
            u_min=u_min,
            v_min=v_min,
            u_max=u_max,
            v_max=v_max,
            z_index=self.get_next_box_z_index()
        )

        return self.add_box(box)

    def add_box(self, box):
        self.boxes_by_id[box.id] = box
        self.box_order.append(box.id)
        self.active_box_id = box.id
        return box

    def delete_box(self, box_id):
        if not box_id:
            return False

        if box_id not in self.boxes_by_id:
            return False

        del self.boxes_by_id[box_id]

        self.box_order = [
            existing_id
            for existing_id in self.box_order
            if existing_id != box_id
        ]

        if self.active_box_id == box_id:
            if self.box_order:
                self.active_box_id = self.box_order[-1]
            else:
                self.active_box_id = None

        return True

    def delete_active_box(self):
        return self.delete_box(self.active_box_id)

    def clear_boxes(self):
        self.boxes_by_id = {}
        self.box_order = []
        self.active_box_id = None

    # -----------------------------------------------------
    # Access
    # -----------------------------------------------------

    def set_active_box(self, box_id):
        if box_id in self.boxes_by_id:
            self.active_box_id = box_id
            return True

        return False

    def get_box(self, box_id):
        return self.boxes_by_id.get(box_id)

    def get_active_box(self):
        return self.get_box(self.active_box_id)

    def iter_boxes(self):
        for box_id in self.box_order:
            box = self.boxes_by_id.get(box_id)

            if box:
                yield box
    def iter_boxes_by_z(self):
        """
        Iterate boxes in z-index order.

        Lower z-index draws first.
        Higher z-index draws later.
        """

        boxes = [
            self.boxes_by_id[box_id]
            for box_id in self.box_order
            if box_id in self.boxes_by_id
        ]

        boxes.sort(
            key=lambda box: getattr(box, "z_index", 0)
        )

        for box in boxes:
            yield box
    # -----------------------------------------------------
    # Serialization prep
    # -----------------------------------------------------

    def to_dict(self):
        return {
            "version": self.version,
            "texture_path": self.texture_path,
            "texture_resolution": self.texture_resolution,
            "active_box_id": self.active_box_id,
            "boxes": [
                box.to_dict()
                for box in self.iter_boxes()
            ]
        }


_MODEL = None


def get_model():
    global _MODEL

    if _MODEL is None:
        _MODEL = ETrimModel()

    return _MODEL


def reset_model():
    global _MODEL
    _MODEL = ETrimModel()
    return _MODEL