from sources.royalroad import RoyalRoadSource
from sources.scriblehub import ScribbleHubSource
from sources.wuxiaspot import WuxiaSpotSource

REGISTRY = {
    "royalroad": RoyalRoadSource(),
    "scribblehub": ScribbleHubSource(),
    "wuxiaspot": WuxiaSpotSource(),
}
