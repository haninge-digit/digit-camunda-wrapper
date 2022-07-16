from functools import wraps
import logging
import sanic
import jwt


# def check_token(request):
#     if not request.token:
#         return False

#     try:
#         jwt.decode(
#             request.token, request.app.config.secret, algorithms=["HS256"]
#         )
#     except jwt.exceptions.InvalidTokenError:
#         return False
#     else:
#         return True

def token_is_valid(request) -> bool:
    if request.app.ctx.disable_auth:    # Authentication is disabled
        return True
    if not request.token:
        logging.error("Missing JWT token in request")
        return False
    try:
        jwt.decode(request.token, request.app.ctx.jwt_secret, options={'require':["exp"]}, algorithms="HS256")
    except jwt.InvalidSignatureError:
        logging.error("JWT token has an invalid signature")
        return False        # Missing JWT token in request
    except jwt.ExpiredSignatureError:
        logging.error("JWT token has expired")
        return False
    except jwt.MissingRequiredClaimError:
        logging.error("Missing 'exp' claim in JWT token")
        return False

    return True     # All good!


def protected(wrapped):
    def decorator(f):
        @wraps(f)
        async def decorated_function(request, *args, **kwargs):
            if token_is_valid(request):
                return await f(request, *args, **kwargs)
            else:
                return sanic.text("Unauthorized", 401)
        return decorated_function
    return decorator(wrapped)

