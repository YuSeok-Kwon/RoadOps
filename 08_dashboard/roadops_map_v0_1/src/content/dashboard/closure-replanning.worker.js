import network from "../assets/routing-network.json";
import { replanClosure } from "./closure-replanning.js";

self.onmessage = ({ data }) => {
  const { requestId, input } = data;
  try { self.postMessage({ requestId, result: replanClosure({ network, ...input }) }); }
  catch { self.postMessage({ requestId, result: { status: "fail", routes: [], message: "대체 경로 계산에 실패했습니다. 입력을 확인하고 다시 계산해 주세요." } }); }
};
