from typing import Any

from http_2.context import ConnectionContext, RequestContext


class ArgumentResolver:

    @staticmethod
    def resolve(required_params: list[str],
                annotations: dict[str, type],
                connection_ctx: ConnectionContext,
                request_ctx: RequestContext) -> dict[str, Any]:
        params = {}

        for required_param in required_params:
            if param_type := annotations.get(required_param, None):
                if obj_in_req_ctx := request_ctx.find_param_with_type(required_param, param_type):
                    params[required_param] = obj_in_req_ctx
                elif obj_in_req_ctx := request_ctx.find_param(required_param):
                    params[required_param] = obj_in_req_ctx
                elif obj_in_conn_ctx := connection_ctx.find_param_with_type(required_param, param_type):
                    params[required_param] = obj_in_conn_ctx
                elif obj_in_conn_ctx := connection_ctx.find_param(required_param):
                    params[required_param] = obj_in_conn_ctx
                else:
                    params[required_param] = None
            else:
                if obj_in_req_ctx := request_ctx.find_param(required_param):
                    params[required_param] = obj_in_req_ctx
                elif obj_in_conn_ctx := connection_ctx.find_param(required_param):
                    params[required_param] = obj_in_conn_ctx
                else:
                    params[required_param] = None

        return params
