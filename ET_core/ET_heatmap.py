# ET_core/ET_heatmap.py

class EStretchHeatMapCalculator(object):
    """
    Calculates UV stretch metrics for cached preview UV data.

    This class does not draw.
    This class does not know about Qt.
    This class does not modify mesh_data.

    It only returns:
        {
            (id(mesh_data), face_index): stretch_value
        }

    stretch_value:
        1.0 = neutral
        >1.0 = increasingly stretched/compressed
    """

    EPSILON = 0.000000001

    def __init__(self):
        self.metrics = {}
        self.ratios = {}
        self.densities = {}
        self.median_density = 0.0

    # -----------------------------------------------------
    # Geometry helpers
    # -----------------------------------------------------

    @staticmethod
    def triangle_area_3d(point_a, point_b, point_c):
        """
        Return triangle area from OpenMaya points/vectors.
        """

        vector_ab = point_b - point_a
        vector_ac = point_c - point_a
        cross = vector_ab ^ vector_ac

        return float(cross.length() * 0.5)

    @classmethod
    def polygon_area_3d(cls, points):
        """
        Compute polygon area by fan triangulation.
        """

        if not points:
            return 0.0

        if len(points) < 3:
            return 0.0

        origin = points[0]
        area = 0.0

        for index in range(1, len(points) - 1):
            area += cls.triangle_area_3d(
                origin,
                points[index],
                points[index + 1]
            )

        return float(area)

    @staticmethod
    def polygon_area_uv(uv_points):
        """
        Compute absolute 2D polygon UV area using shoelace formula.

        uv_points:
            [(u, v), ...]
        """

        if not uv_points:
            return 0.0

        if len(uv_points) < 3:
            return 0.0

        area = 0.0
        count = len(uv_points)

        for index, point_a in enumerate(uv_points):
            point_b = uv_points[(index + 1) % count]

            u_a, v_a = point_a
            u_b, v_b = point_b

            area += (u_a * v_b) - (u_b * v_a)

        return abs(area) * 0.5

    @staticmethod
    def median(values):
        values = [
            float(value)
            for value in values
            if value is not None
        ]

        if not values:
            return 0.0

        values.sort()

        middle = len(values) // 2

        if len(values) % 2:
            return values[middle]

        return (values[middle - 1] + values[middle]) * 0.5

    # -----------------------------------------------------
    # UV helpers
    # -----------------------------------------------------

    def get_uv_position(self, mesh_data, uv_id):
        if (
            hasattr(mesh_data, "preview_uv_positions") and
            uv_id in mesh_data.preview_uv_positions
        ):
            return mesh_data.preview_uv_positions[uv_id]

        return mesh_data.uv_positions[uv_id]

    def get_face_uv_points(self, mesh_data, face_uv_ids):
        result = []

        for uv_id in face_uv_ids:
            result.append(
                self.get_uv_position(
                    mesh_data,
                    uv_id
                )
            )

        return result

    # -----------------------------------------------------
    # Main calculation
    # -----------------------------------------------------

    def compute(self, uv_cache):
        """
        Compute stretch metrics for all cached faces.

        Metric:
            density = uv_area / world_area

        Then compare every face density against median density:

            ratio = density / median_density

            stretch = max(ratio, 1.0 / ratio)

        This treats both compression and expansion as stretch.
        """

        self.metrics = {}
        self.ratios = {}
        self.densities = {}
        self.median_density = 0.0


        if not uv_cache:
            return self.metrics

        if not uv_cache.has_data():
            return self.metrics

        densities = []

        for mesh_data in uv_cache.meshes:
            world_areas = getattr(
                mesh_data,
                "face_world_areas",
                []
            )

            for face_index, face_uv_ids in enumerate(mesh_data.faces):
                if face_index >= len(world_areas):
                    continue

                world_area = float(world_areas[face_index])

                if world_area <= self.EPSILON:
                    continue

                uv_points = self.get_face_uv_points(
                    mesh_data,
                    face_uv_ids
                )

                uv_area = self.polygon_area_uv(
                    uv_points
                )

                if uv_area <= self.EPSILON:
                    continue

                densities.append(
                    uv_area / world_area
                )

        median_density = self.median(
            densities
        )

        self.median_density = median_density

        if median_density <= self.EPSILON:
            return self.metrics

        for mesh_data in uv_cache.meshes:
            world_areas = getattr(
                mesh_data,
                "face_world_areas",
                []
            )

            for face_index, face_uv_ids in enumerate(mesh_data.faces):
                key = (
                    id(mesh_data),
                    face_index
                )

                if face_index >= len(world_areas):
                    self.densities[key] = 0.0
                    self.ratios[key] = 1.0
                    self.metrics[key] = 1.0
                    continue

                world_area = float(world_areas[face_index])

                uv_points = self.get_face_uv_points(
                    mesh_data,
                    face_uv_ids
                )

                uv_area = self.polygon_area_uv(
                    uv_points
                )

                if world_area <= self.EPSILON or uv_area <= self.EPSILON:
                    self.densities[key] = 0.0
                    self.ratios[key] = 999.0
                    self.metrics[key] = 999.0
                    continue

                density = uv_area / world_area

                self.densities[key] = density

                ratio = density / median_density
                self.ratios[key] = ratio

                if ratio <= self.EPSILON:
                    stretch = 999.0
                    self.densities[key] = 0.0
                    self.ratios[key] = 999.0
                    self.metrics[key] = 999.0
                    continue
                else:
                    stretch = max(
                        ratio,
                        1.0 / ratio
                    )

                self.metrics[key] = stretch

        return self.metrics

    def get_face_density(self, mesh_data, face_index):
        return self.densities.get(
            (
                id(mesh_data),
                face_index
            ),
            0.0
        )


    def get_face_density_ratio(self, mesh_data, face_index, reference_median_density=None):
        """
        Return signed density ratio.

        If reference_median_density is provided, compare against that fixed baseline.
        Otherwise use this calculator's current median_density.
        """

        density = self.get_face_density(
            mesh_data,
            face_index
        )

        if reference_median_density is None:
            reference_median_density = self.median_density

        if reference_median_density <= self.EPSILON:
            return 1.0

        if density <= self.EPSILON:
            return 999.0

        return density / reference_median_density

    def get_face_stretch(self, mesh_data, face_index):
        return self.metrics.get(
            (
                id(mesh_data),
                face_index
            ),
            1.0
        )