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


    def clamp_value(self, value, minimum, maximum):
        return max(minimum, min(maximum, value))


    def sanitize_box_size(self, width, height):
        """
        Clamp requested size into valid 0-1 UV size.
        """

        width = float(width)
        height = float(height)

        width = self.clamp_value(width, 0.001, 1.0)
        height = self.clamp_value(height, 0.001, 1.0)

        return width, height


    def make_rect_from_origin(self, u_min, v_min, width, height):
        """
        Create rect from bottom-left corner and size.
        """

        width, height = self.sanitize_box_size(
            width,
            height
        )

        u_min = self.clamp_value(float(u_min), 0.0, 1.0 - width)
        v_min = self.clamp_value(float(v_min), 0.0, 1.0 - height)

        u_max = u_min + width
        v_max = v_min + height

        return (
            round(u_min, 5),
            round(v_min, 5),
            round(u_max, 5),
            round(v_max, 5)
        )


    def make_rect_centered(self, center_u, center_v, width, height):
        """
        Create rect centered on a point, clamped inside 0-1.
        """

        width, height = self.sanitize_box_size(
            width,
            height
        )

        u_min = float(center_u) - width * 0.5
        v_min = float(center_v) - height * 0.5

        return self.make_rect_from_origin(
            u_min,
            v_min,
            width,
            height
        )


    def find_free_box_rect(self, width, height, preferred_u=0.0, preferred_v=0.0):
        """
        Find a free non-overlapping rect of exact requested size.

        Search starts near preferred_u/preferred_v.
        If preferred location is occupied, search closest available position.

        Returns:
            (u_min, v_min, u_max, v_max)
            or None.
        """

        width, height = self.sanitize_box_size(
            width,
            height
        )

        # First try exact preferred position.
        preferred_rect = self.make_rect_from_origin(
            preferred_u,
            preferred_v,
            width,
            height
        )

        if self.box_area_is_free(*preferred_rect):
            return preferred_rect

        step = 0.025

        max_u = 1.0 - width
        max_v = 1.0 - height

        if max_u < 0.0 or max_v < 0.0:
            return None

        candidates = []

        v = 0.0
        while v <= max_v + 0.0001:
            u = 0.0

            while u <= max_u + 0.0001:
                rect = self.make_rect_from_origin(
                    u,
                    v,
                    width,
                    height
                )

                if self.box_area_is_free(*rect):
                    distance_sq = (
                        (rect[0] - preferred_rect[0]) *
                        (rect[0] - preferred_rect[0])
                    ) + (
                        (rect[1] - preferred_rect[1]) *
                        (rect[1] - preferred_rect[1])
                    )

                    candidates.append(
                        (
                            distance_sq,
                            rect
                        )
                    )

                u += step

            v += step

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[0][1]


    def find_best_fitting_box_rect(self, width, height, preferred_u=0.0, preferred_v=0.0):
        """
        Find the biggest possible box that fits without overlap.

        Starts with requested size.
        If requested size does not fit, shrink proportionally until it fits.
        """

        width, height = self.sanitize_box_size(
            width,
            height
        )

        # Try requested size first.
        rect = self.find_free_box_rect(
            width,
            height,
            preferred_u=preferred_u,
            preferred_v=preferred_v
        )

        if rect:
            return rect

        # Shrink proportionally until it fits.
        scale = 0.95

        current_width = width
        current_height = height

        while current_width >= 0.001 and current_height >= 0.001:
            current_width *= scale
            current_height *= scale

            rect = self.find_free_box_rect(
                current_width,
                current_height,
                preferred_u=preferred_u,
                preferred_v=preferred_v
            )

            if rect:
                return rect

        return None


    def create_box(self, width=0.20, height=0.20, preferred_u=0.0, preferred_v=0.0, centered=False):
        """
        Create a new trim box.

        Rules:
            - Use requested width/height if possible.
            - Try requested/preferred position first.
            - If that position is occupied, find the closest free position.
            - If requested size cannot fit anywhere, shrink until it fits.
            - Never overlap.
            - Never go outside 0-1.

        Args:
            width:
                Width in UV space. 1.0 equals 100 percent of tile.

            height:
                Height in UV space. 1.0 equals 100 percent of tile.

            preferred_u/preferred_v:
                Preferred creation point.

            centered:
                If True, preferred_u/preferred_v is treated as center.
                If False, preferred_u/preferred_v is treated as bottom-left origin.

        Returns:
            TrimBox or None
        """

        width, height = self.sanitize_box_size(
            width,
            height
        )

        if centered:
            preferred_rect = self.make_rect_centered(
                preferred_u,
                preferred_v,
                width,
                height
            )

            preferred_u = preferred_rect[0]
            preferred_v = preferred_rect[1]

        rect = self.find_best_fitting_box_rect(
            width,
            height,
            preferred_u=preferred_u,
            preferred_v=preferred_v
        )

        if not rect:
            print("[eTrim] Could not create box. No free area available.")
            return None

        u_min, v_min, u_max, v_max = rect

        index = len(self.box_order) + 1

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