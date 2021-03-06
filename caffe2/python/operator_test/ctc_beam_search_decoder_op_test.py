from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from caffe2.python import core
from collections import defaultdict, Counter
from hypothesis import given
import caffe2.python.hypothesis_test_util as hu
import hypothesis.strategies as st
import numpy as np

import unittest

DEFAULT_BEAM_WIDTH = 10
DEFAULT_PRUNE_THRESHOLD = 0.001


class TestCTCBeamSearchDecoderOp(hu.HypothesisTestCase):

    @given(
        batch=st.sampled_from([1, 2, 4]),
        max_time=st.sampled_from([1, 8, 64]),
        alphabet_size=st.sampled_from([1, 2, 32, 128, 512]),
        beam_width=st.sampled_from([1, 2, 16, None]),
        **hu.gcs_cpu_only
    )
    def test_ctc_beam_search_decoder(
        self, batch, max_time,
        alphabet_size, beam_width, gc, dc
    ):
        if not beam_width:
            beam_width = DEFAULT_BEAM_WIDTH
            op_seq_len = core.CreateOperator('CTCBeamSearchDecoder',
                ['INPUTS', 'SEQ_LEN'],
                ['OUTPUT_LEN', 'VALUES'])

            op_no_seq_len = core.CreateOperator('CTCBeamSearchDecoder',
                ['INPUTS'],
                ['OUTPUT_LEN', 'VALUES'])
        else:
            op_seq_len = core.CreateOperator('CTCBeamSearchDecoder',
                ['INPUTS', 'SEQ_LEN'],
                ['OUTPUT_LEN', 'VALUES'],
                beam_width=beam_width)

            op_no_seq_len = core.CreateOperator('CTCBeamSearchDecoder',
                ['INPUTS'],
                ['OUTPUT_LEN', 'VALUES'],
                beam_width=beam_width)

        def input_generater():
            inputs = np.random.rand(max_time, batch, alphabet_size)\
                .astype(np.float32)
            seq_len = np.random.randint(1, max_time + 1, size=batch)\
                .astype(np.int32)
            return inputs, seq_len

        def ref_ctc_decoder(inputs, seq_len):
            output_len = np.array([]).astype(np.int32)
            val = np.array([]).astype(np.int32)

            for i in range(batch):
                Pb, Pnb = defaultdict(Counter), defaultdict(Counter)
                Pb[0][()] = 1
                Pnb[0][()] = 0
                A_prev = [()]
                ctc = inputs[:, i, :]
                ctc = np.vstack((np.zeros(alphabet_size), ctc))
                len_i = seq_len[i] if seq_len is not None else max_time

                for t in range(1, len_i + 1):
                    pruned_alphabet = np.where(ctc[t] > DEFAULT_PRUNE_THRESHOLD)[0]
                    for l in A_prev:
                        for c in pruned_alphabet:
                            if c == 0:
                                Pb[t][l] += ctc[t][c] * (Pb[t - 1][l] + Pnb[t - 1][l])
                            else:
                                l_plus = l + (c,)
                                if len(l) > 0 and c == l[-1]:
                                    Pnb[t][l_plus] += ctc[t][c] * Pb[t - 1][l]
                                    Pnb[t][l] += ctc[t][c] * Pnb[t - 1][l]
                                else:
                                    Pnb[t][l_plus] += \
                                        ctc[t][c] * (Pb[t - 1][l] + Pnb[t - 1][l])

                                if l_plus not in A_prev:
                                    Pb[t][l_plus] += \
                                        ctc[t][0] * \
                                        (Pb[t - 1][l_plus] + Pnb[t - 1][l_plus])
                                    Pnb[t][l_plus] += ctc[t][c] * Pnb[t - 1][l_plus]

                    A_next = Pb[t] + Pnb[t]
                    A_prev = sorted(A_next, key=A_next.get, reverse=True)
                    A_prev = A_prev[:beam_width]

                decoded = A_prev[0] if len(A_prev) > 0 else ()

                val = np.hstack((val, decoded))
                output_len = np.append(output_len, len(decoded))

            return [output_len, val]

        def ref_ctc_decoder_max_time(inputs):
            return ref_ctc_decoder(inputs, None)

        inputs, seq_len = input_generater()

        self.assertReferenceChecks(
            device_option=gc,
            op=op_seq_len,
            inputs=[inputs, seq_len],
            reference=ref_ctc_decoder,
        )

        self.assertReferenceChecks(
            device_option=gc,
            op=op_no_seq_len,
            inputs=[inputs],
            reference=ref_ctc_decoder_max_time,
        )


if __name__ == "__main__":
    import random
    random.seed(2603)
    unittest.main()
