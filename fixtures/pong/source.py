import argparse
import json
import sys

FIELD_WIDTH = 600
FIELD_HEIGHT = 400
PADDLE_LENGTH = 60
PADDLE_LEFT_X = 20
PADDLE_RIGHT_X = 580
BALL_SIZE = 6
BALL_RADIUS = BALL_SIZE // 2

HALF_PADDLE = PADDLE_LENGTH / 2
FIELD_CENTER_X = FIELD_WIDTH // 2
FIELD_CENTER_Y = FIELD_HEIGHT // 2


def step(state):
    state["ball_x"] += state["ball_dx"]
    state["ball_y"] += state["ball_dy"]

    bx = state["ball_x"]
    by = state["ball_y"]
    bdx = state["ball_dx"]
    bdy = state["ball_dy"]

    if by - BALL_RADIUS <= 0:
        state["ball_y"] = BALL_RADIUS
        state["ball_dy"] = -bdy
    elif by + BALL_RADIUS >= FIELD_HEIGHT:
        state["ball_y"] = FIELD_HEIGHT - BALL_RADIUS
        state["ball_dy"] = -bdy

    bx = state["ball_x"]
    by = state["ball_y"]
    bdx = state["ball_dx"]

    if bdx < 0 and bx - BALL_RADIUS <= PADDLE_LEFT_X <= bx + BALL_RADIUS:
        if state["paddle_left"] - HALF_PADDLE <= by <= state["paddle_left"] + HALF_PADDLE:
            state["ball_dx"] = -bdx
            state["ball_x"] = PADDLE_LEFT_X + BALL_RADIUS

    if bdx > 0 and bx - BALL_RADIUS <= PADDLE_RIGHT_X <= bx + BALL_RADIUS:
        if state["paddle_right"] - HALF_PADDLE <= by <= state["paddle_right"] + HALF_PADDLE:
            state["ball_dx"] = -bdx
            state["ball_x"] = PADDLE_RIGHT_X - BALL_RADIUS

    bx = state["ball_x"]

    if bx + BALL_RADIUS <= 0:
        state["score_right"] += 1
        state["ball_x"] = FIELD_CENTER_X
        state["ball_y"] = FIELD_CENTER_Y
    elif bx - BALL_RADIUS >= FIELD_WIDTH:
        state["score_left"] += 1
        state["ball_x"] = FIELD_CENTER_X
        state["ball_y"] = FIELD_CENTER_Y

    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ball-x", type=int, required=True)
    parser.add_argument("--ball-y", type=int, required=True)
    parser.add_argument("--ball-dx", type=int, required=True)
    parser.add_argument("--ball-dy", type=int, required=True)
    parser.add_argument("--paddle-left", type=int, required=True)
    parser.add_argument("--paddle-right", type=int, required=True)
    parser.add_argument("--score-left", type=int, required=True)
    parser.add_argument("--score-right", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(1)

    if not (0 <= args.ball_x <= FIELD_WIDTH):
        sys.exit(1)
    if not (0 <= args.ball_y <= FIELD_HEIGHT):
        sys.exit(1)
    if not (0 <= args.paddle_left <= FIELD_HEIGHT):
        sys.exit(1)
    if not (0 <= args.paddle_right <= FIELD_HEIGHT):
        sys.exit(1)
    if args.frames < 0:
        sys.exit(1)

    state = {
        "ball_x": args.ball_x,
        "ball_y": args.ball_y,
        "ball_dx": args.ball_dx,
        "ball_dy": args.ball_dy,
        "paddle_left": args.paddle_left,
        "paddle_right": args.paddle_right,
        "score_left": args.score_left,
        "score_right": args.score_right,
    }

    for _ in range(args.frames):
        step(state)

    print(json.dumps(state))
    sys.exit(0)


if __name__ == "__main__":
    main()
