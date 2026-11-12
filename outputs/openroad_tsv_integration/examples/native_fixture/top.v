module bottom_chip(sig0, sig1); inout sig0, sig1; endmodule
module top_chip(sig0, sig1); inout sig0, sig1; endmodule
module synthetic_tsv_top();
wire signal0, signal1;
bottom_chip bottom_die(.sig0(signal0), .sig1(signal1));
top_chip top_die(.sig0(signal0), .sig1(signal1));
endmodule
