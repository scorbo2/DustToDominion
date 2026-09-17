# Dust to Dominion - project overview

"Dust to Dominion" is a game written in Python using the `pygame-ce` library.
The player starts with a single, poorly-equipped mining spaceship, and must
venture into dangerous asteroid fields with the goal of splitting apart the
asteroids to collect precious minerals which can then be sold for money.
The player can purchase ship upgrades, and eventually can afford to but
a new and more capable ship. The ultimate goal of the game is to build a
successful mining operation with a fleet of vessels. The game is divided
into two main elements:

- **Tactical view**: the player controls a single mining vessel
  armed with various weaponry. A top-down 2D view is provided,
  and the player must dodge asteroids, fight off rival mining
  ships, and attempt to collect precious minerals.
- **Strategic view**: the player must make resource allocation
  decisions to purchase better equipment for their existing
  ships, or purchase new ships. The player can also hire crew
  for their ships, which improve ship stats.

The name of the game describes the journey of starting with nothing
but asteroid dust, and ending up with a dominant mining fleet operation.

## Logging

The game will use loguru for logging.

## Testing

The game will have a fully hermetic test suite. A feature is not complete
unless it has reasonably comprehensive unit tests.

