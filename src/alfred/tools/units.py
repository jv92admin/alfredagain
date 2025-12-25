"""
Alfred V2 - Unit Handling.

Skeleton for unit parsing and conversion.
Currently pass-through; expand later with real conversion logic.
"""

from dataclasses import dataclass


@dataclass
class ParsedQuantity:
    """A parsed quantity with value and unit."""

    value: float
    unit: str
    original: str  # Original input for reference


class UnitHandler:
    """
    Skeleton for unit handling.

    Currently provides pass-through methods.
    Expand later with real conversion logic.
    """

    # Unit categories for future conversion
    VOLUME_UNITS = {"cup", "tbsp", "tsp", "ml", "l", "fl oz", "gallon", "pint", "quart"}
    WEIGHT_UNITS = {"lb", "oz", "g", "kg"}
    COUNT_UNITS = {"piece", "item", "can", "bottle", "carton", "bag", "box", "bunch", "head", "clove"}

    @staticmethod
    def parse(quantity: float | str, unit: str) -> ParsedQuantity:
        """
        Parse and normalize a quantity and unit.

        Currently pass-through; stores original for reference.

        Args:
            quantity: Numeric quantity (or string to parse)
            unit: Unit of measurement

        Returns:
            ParsedQuantity with normalized values
        """
        if isinstance(quantity, str):
            # Handle fraction strings
            if "/" in quantity:
                parts = quantity.split("/")
                qty = float(parts[0]) / float(parts[1])
            else:
                qty = float(quantity)
        else:
            qty = quantity

        normalized_unit = unit.lower().strip()

        return ParsedQuantity(
            value=qty,
            unit=normalized_unit,
            original=f"{quantity} {unit}",
        )

    @staticmethod
    def convert(value: float, from_unit: str, to_unit: str) -> float:
        """
        Convert between units.

        Currently raises NotImplementedError for different units.
        Same-unit conversion returns value unchanged.

        Args:
            value: Quantity to convert
            from_unit: Source unit
            to_unit: Target unit

        Returns:
            Converted value

        Raises:
            NotImplementedError: If conversion not supported
        """
        from_normalized = from_unit.lower().strip()
        to_normalized = to_unit.lower().strip()

        if from_normalized == to_normalized:
            return value

        # Future: Add actual conversion logic
        # For now, raise to make it clear this isn't implemented
        raise NotImplementedError(
            f"Conversion from '{from_unit}' to '{to_unit}' not yet supported. "
            "Unit conversion will be implemented in a future phase."
        )

    @classmethod
    def are_compatible(cls, unit1: str, unit2: str) -> bool:
        """
        Check if two units are compatible (same category).

        Args:
            unit1: First unit
            unit2: Second unit

        Returns:
            True if units can potentially be converted
        """
        u1 = unit1.lower().strip()
        u2 = unit2.lower().strip()

        # Check if both in same category
        for category in [cls.VOLUME_UNITS, cls.WEIGHT_UNITS, cls.COUNT_UNITS]:
            if u1 in category and u2 in category:
                return True

        return u1 == u2

    @staticmethod
    def format_quantity(value: float, unit: str) -> str:
        """
        Format a quantity for display.

        Args:
            value: Numeric quantity
            unit: Unit of measurement

        Returns:
            Formatted string like "2 cups" or "1.5 lbs"
        """
        # Use whole numbers when possible
        if value == int(value):
            return f"{int(value)} {unit}"
        return f"{value:.2f} {unit}".rstrip("0").rstrip(".")

