import os
from typing import Any

import requests
from fastmcp import FastMCP

mcp = FastMCP("fixify_tools")

SERPAPI_URL = "https://serpapi.com/search.json"


# -----------------------------
# Shared helpers
# -----------------------------

def _api_key() -> str:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        raise RuntimeError("Missing SERPAPI_KEY environment variable")
    return key


def _price_to_number(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "").replace("₹", "").strip()

    try:
        return float(text)
    except ValueError:
        return None


# -----------------------------
# AMAZON PRODUCT TOOLS
# -----------------------------

def _normalise_product(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("title"),
        "price_inr": _price_to_number(item.get("price")),
        "mrp_inr": _price_to_number(item.get("extracted_price")),
        "rating": item.get("rating"),
        "reviews": item.get("reviews"),
        "asin": item.get("asin"),
        "url": item.get("link"),
        "delivery": item.get("delivery"),
    }


@mcp.tool()
def search_products_mat(
    query: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Search Amazon India for products using a natural-language query."""

    query = query.strip()

    if not query:
        raise ValueError("query cannot be empty")

    max_results = max(1, min(int(max_results), 20))

    params = {
        "api_key": _api_key(),
        "engine": "amazon",
        "k": query,
        "amazon_domain": "amazon.in",
        "language": "en_IN",
        "page": 1,
        "output": "json",
    }

    response = requests.get(
        SERPAPI_URL,
        params=params,
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"SerpApi request failed: HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"SerpApi error: {data['error']}"
        )

    organic_results = data.get("organic_results", [])

    products = [
        _normalise_product(item)
        for item in organic_results[:max_results]
    ]

    return {
        "marketplace": "Amazon.in",
        "currency": "INR",
        "query": query,
        "count": len(products),
        "products": products,
        "source": "SerpApi Amazon Search",
    }


@mcp.tool()
def get_products_mat(
    asin: str,
) -> dict[str, Any]:
    """Retrieve current Amazon India product information for a specific ASIN."""

    asin = asin.strip()

    if not asin:
        raise ValueError("asin cannot be empty")

    params = {
        "api_key": _api_key(),
        "engine": "amazon_product",
        "asin": asin,
        "amazon_domain": "amazon.in",
        "language": "en_IN",
        "output": "json",
    }

    response = requests.get(
        SERPAPI_URL,
        params=params,
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"SerpApi request failed: HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"SerpApi error: {data['error']}"
        )

    product = data.get("product_results") or {}

    return {
        "marketplace": "Amazon.in",
        "currency": "INR",
        "asin": asin,
        "product": {
            "name": product.get("title"),
            "price_inr": _price_to_number(
                product.get("price")
            ),
            "mrp_inr": _price_to_number(
                product.get("old_price")
            ),
            "rating": product.get("rating"),
            "reviews": product.get("reviews"),
            "url": product.get("link"),
            "offers": product.get("offers"),
            "emi": product.get("emi"),
        },
        "source": "SerpApi Amazon Product Search",
    }


# -----------------------------
# FINANCE FORECASTING TOOLS
# -----------------------------

def _validate_scenario(
    scenario: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]]]:

    name = str(
        scenario.get(
            "name",
            "Unnamed scenario",
        )
    )

    forecast_months = int(
        scenario.get(
            "forecast_months",
            0,
        )
    )

    costs = scenario.get("costs", [])

    if forecast_months < 0:
        raise ValueError(
            "forecast_months must be >= 0"
        )

    if not isinstance(costs, list):
        raise ValueError(
            "costs must be a list of cost objects"
        )

    normalized = []

    for item in costs:

        if not isinstance(item, dict):
            raise ValueError(
                "Each cost must be an object"
            )

        month = int(
            item.get(
                "month",
                0,
            )
        )

        amount = float(
            item.get(
                "amount",
                0,
            )
        )

        recurring = bool(
            item.get(
                "recurring",
                False,
            )
        )

        frequency = str(
            item.get(
                "frequency",
                "monthly",
            )
        ).lower()

        if month < 0 or month > forecast_months:
            raise ValueError(
                f"Cost month {month} must be between "
                f"0 and forecast_months ({forecast_months})"
            )

        if amount < 0:
            raise ValueError(
                "Cost amount must be >= 0"
            )

        if recurring and frequency not in {
            "monthly",
            "quarterly",
            "yearly",
        }:
            raise ValueError(
                "Recurring frequency must be "
                "monthly, quarterly, or yearly"
            )

        if not recurring:
            frequency = None

        normalized.append(
            {
                "month": month,
                "amount": amount,
                "recurring": recurring,
                "frequency": frequency,
            }
        )

    return (
        name,
        forecast_months,
        normalized,
    )


def _frequency_interval(
    frequency: str,
) -> int:

    intervals = {
        "monthly": 1,
        "quarterly": 3,
        "yearly": 12,
    }

    return intervals[frequency]


def _calculate_scenario(
    scenario: dict[str, Any],
) -> dict[str, Any]:

    (
        name,
        forecast_months,
        costs,
    ) = _validate_scenario(scenario)

    monthly_costs = [
        0.0
        for _ in range(
            forecast_months + 1
        )
    ]

    for cost in costs:

        start_month = cost["month"]
        amount = cost["amount"]

        if not cost["recurring"]:
            monthly_costs[start_month] += amount
            continue

        interval = _frequency_interval(
            cost["frequency"]
        )

        month = start_month

        while month <= forecast_months:
            monthly_costs[month] += amount
            month += interval

    total_cost = sum(monthly_costs)

    if forecast_months > 0:
        average_monthly_cost = (
            total_cost / forecast_months
        )
    else:
        average_monthly_cost = total_cost

    return {
        "name": name,
        "forecast_months": forecast_months,
        "total_cost": round(
            total_cost,
            2,
        ),
        "average_monthly_cost": round(
            average_monthly_cost,
            2,
        ),
        "costs_by_month": [
            {
                "month": month,
                "cost": round(
                    amount,
                    2,
                ),
            }
            for month, amount in enumerate(
                monthly_costs
            )
            if amount != 0
        ],
    }


@mcp.tool()
def forecast_scenario(
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """
    Forecast one scenario over a defined period.

    Supports:
    - one-time costs
    - monthly recurring costs
    - quarterly recurring costs
    - yearly recurring costs

    The tool performs deterministic calculations only.
    It does not recommend an option.
    """

    return _calculate_scenario(
        scenario
    )


@mcp.tool()
def compare_scenarios(
    forecast_months: int,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare multiple scenarios over the same period.

    The tool calculates each scenario.
    It does not recommend a winner.
    """

    if forecast_months < 0:
        raise ValueError(
            "forecast_months must be >= 0"
        )

    if (
        not isinstance(scenarios, list)
        or not scenarios
    ):
        raise ValueError(
            "scenarios must be a non-empty list"
        )

    results = []

    for scenario in scenarios:

        scenario_with_period = dict(
            scenario
        )

        scenario_with_period[
            "forecast_months"
        ] = forecast_months

        results.append(
            _calculate_scenario(
                scenario_with_period
            )
        )

    return {
        "forecast_months": forecast_months,
        "scenarios": results,
    }


# -----------------------------
# SERVER
# -----------------------------

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "8000",
        )
    )

    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
    )
