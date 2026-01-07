import numpy as np

# Print debug matrices (WARNING: extremely verbose)
P_O = False


def Calculation_Position_2D_TDOA_6_Adjustment(OPe, H1, H2, H3, H4, D12, D13, D14, D23, D24, D34,
                                              BS12, BS13, BS14, BS23, BS24, BS34):
    P = np.zeros((6, 6))
    P[0, 0] = 1.0 / (BS12 * BS12)
    P[1, 1] = 1.0 / (BS13 * BS13)
    P[2, 2] = 1.0 / (BS14 * BS14)
    P[3, 3] = 1.0 / (BS23 * BS23)
    P[4, 4] = 1.0 / (BS24 * BS24)
    P[5, 5] = 1.0 / (BS34 * BS34)

    if P_O:
        print("P = ", P)

    V1 = np.zeros((6, 1))
    Vd = np.zeros((6, 1))
    A = np.zeros((6, 2))
    L = np.zeros((6, 1))
    ATPA = np.zeros((3, 2))
    ATPA1 = np.zeros((2, 2))
    iter = 0
    stop_iter = False
    eV = 1.0e-10
    er = 1

    while iter < 1000:
        d1 = np.linalg.norm(OPe - H1)
        d2 = np.linalg.norm(OPe - H2)
        d3 = np.linalg.norm(OPe - H3)
        d4 = np.linalg.norm(OPe - H4)

        if d1 == 0: d1 = 1.0e-15
        if d2 == 0: d2 = 1.0e-15
        if d3 == 0: d3 = 1.0e-15
        if d4 == 0: d4 = 1.0e-15

        A[0, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H2[0, 0]) / d2)
        A[0, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H2[1, 0]) / d2)
        A[1, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H3[0, 0]) / d3)
        A[1, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H3[1, 0]) / d3)
        A[2, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H4[0, 0]) / d4)
        A[2, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H4[1, 0]) / d4)
        A[3, 0] = ((OPe[0, 0] - H2[0, 0]) / d2) - ((OPe[0, 0] - H3[0, 0]) / d3)
        A[3, 1] = ((OPe[1, 0] - H2[1, 0]) / d2) - ((OPe[1, 0] - H3[1, 0]) / d3)
        A[4, 0] = ((OPe[0, 0] - H2[0, 0]) / d2) - ((OPe[0, 0] - H4[0, 0]) / d4)
        A[4, 1] = ((OPe[1, 0] - H2[1, 0]) / d2) - ((OPe[1, 0] - H4[1, 0]) / d4)
        A[5, 0] = ((OPe[0, 0] - H3[0, 0]) / d3) - ((OPe[0, 0] - H4[0, 0]) / d4)
        A[5, 1] = ((OPe[1, 0] - H3[1, 0]) / d3) - ((OPe[1, 0] - H4[1, 0]) / d4)

        if P_O:
            print("A = ", A)

        d12 = d1 - d2
        d13 = d1 - d3
        d14 = d1 - d4
        d23 = d2 - d3
        d24 = d2 - d4
        d34 = d3 - d4

        L[0, 0] = d12 - D12
        L[1, 0] = d13 - D13
        L[2, 0] = d14 - D14
        L[3, 0] = d23 - D23
        L[4, 0] = d24 - D24
        L[5, 0] = d34 - D34

        if P_O:
            print("L = ", L)

        ATP = A.T.dot(P)
        ATPA = ATP.dot(A)

        if P_O:
            print("APTA = ", ATPA)

        ATPL = ATP.dot(L)

        if P_O:
            print("ATPL = ", ATPL)

        try:
            ATPA1 = np.linalg.inv(ATPA)
        except np.linalg.LinAlgError:
            if P_O:
                print("macierz ATPA nie jest odwracalna")
            er = 2
            return OPe, 0, 0, 0, 0, 0, 0, 0, er
        else:
            dx = -ATPA1.dot(ATPL)

        if P_O:
            print("dx = ", dx)

        Ad = A.dot(dx)
        V = Ad + L

        if P_O:
            print("V = ", V)

        if iter > 0:
            stop_iter = True
            Vd = np.absolute(V - V1)
            if Vd.max() > eV:
                stop_iter = False

        OPe[0, 0] += dx[0, 0]
        OPe[1, 0] += dx[1, 0]

        V1 = V

        iter += 1

        if stop_iter:
            er = 0
            break

    VTP = V.T.dot(P)
    s = VTP.dot(V)
    mo2 = s.item(0) / (6 - 2.0)

    Cx = np.dot(mo2, ATPA1)
    M = np.sqrt(Cx[0, 0] + Cx[1, 1])
    Mx = np.sqrt(Cx[0, 0])
    My = np.sqrt(Cx[1, 1])

    DEL = ((ATPA[0, 0] - ATPA[1, 1]) * (ATPA[0, 0] - ATPA[1, 1])) + (4.0 * ATPA[0, 1] * ATPA[0, 1])
    li1 = (ATPA[0, 0] + ATPA[1, 1] - np.sqrt(DEL)) / 2.0
    li2 = (ATPA[0, 0] + ATPA[1, 1] + np.sqrt(DEL)) / 2.0
    fi_e = (np.rad2deg(np.arctan((2.0 * ATPA[0, 1] / (ATPA[0, 0] - ATPA[1, 1]))))) / 2.0

    f = 1.53553
    a_e = np.sqrt(mo2) * np.sqrt((2.0 * f) / li1)
    b_e = np.sqrt(mo2) * np.sqrt((2.0 * f) / li2)

    return OPe, mo2, M, Mx, My, fi_e, a_e, b_e, er


def Calculation_Position_2D_TDOA_6_Robust_Adjustment(OPe, H1, H2, H3, H4, D12, D13, D14, D23, D24, D34,
                                                     BS12, BS13, BS14, BS23, BS24, BS34):
    P = np.zeros((6, 6))
    P[0, 0] = 1.0 / (BS12 * BS12)
    P[1, 1] = 1.0 / (BS13 * BS13)
    P[2, 2] = 1.0 / (BS14 * BS14)
    P[3, 3] = 1.0 / (BS23 * BS23)
    P[4, 4] = 1.0 / (BS24 * BS24)
    P[5, 5] = 1.0 / (BS34 * BS34)

    if P_O:
        print("P = ", P)

    V1 = np.zeros((6, 1))
    Vd = np.zeros((6, 1))
    A = np.zeros((6, 2))
    L = np.zeros((6, 1))
    ATPA = np.zeros((3, 2))
    ATPA1 = np.zeros((2, 2))
    iter = 0
    stop_iter = False
    eV = 1.0e-10
    er = 1
    Cv = np.zeros((6, 6))
    Vv = np.zeros((6, 1))
    T = np.identity(6)
    k = 2.0

    d1 = np.linalg.norm(OPe - H1)
    d2 = np.linalg.norm(OPe - H2)
    d3 = np.linalg.norm(OPe - H3)
    d4 = np.linalg.norm(OPe - H4)

    if d1 == 0: d1 = 1.0e-15
    if d2 == 0: d2 = 1.0e-15
    if d3 == 0: d3 = 1.0e-15
    if d4 == 0: d4 = 1.0e-15

    A[0, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H2[0, 0]) / d2)
    A[0, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H2[1, 0]) / d2)
    A[1, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H3[0, 0]) / d3)
    A[1, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H3[1, 0]) / d3)
    A[2, 0] = ((OPe[0, 0] - H1[0, 0]) / d1) - ((OPe[0, 0] - H4[0, 0]) / d4)
    A[2, 1] = ((OPe[1, 0] - H1[1, 0]) / d1) - ((OPe[1, 0] - H4[1, 0]) / d4)
    A[3, 0] = ((OPe[0, 0] - H2[0, 0]) / d2) - ((OPe[0, 0] - H3[0, 0]) / d3)
    A[3, 1] = ((OPe[1, 0] - H2[1, 0]) / d2) - ((OPe[1, 0] - H3[1, 0]) / d3)
    A[4, 0] = ((OPe[0, 0] - H2[0, 0]) / d2) - ((OPe[0, 0] - H4[0, 0]) / d4)
    A[4, 1] = ((OPe[1, 0] - H2[1, 0]) / d2) - ((OPe[1, 0] - H4[1, 0]) / d4)
    A[5, 0] = ((OPe[0, 0] - H3[0, 0]) / d3) - ((OPe[0, 0] - H4[0, 0]) / d4)
    A[5, 1] = ((OPe[1, 0] - H3[1, 0]) / d3) - ((OPe[1, 0] - H4[1, 0]) / d4)

    if P_O:
        print("A = ", A)

    d12 = d1 - d2
    d13 = d1 - d3
    d14 = d1 - d4
    d23 = d2 - d3
    d24 = d2 - d4
    d34 = d3 - d4

    L[0, 0] = d12 - D12
    L[1, 0] = d13 - D13
    L[2, 0] = d14 - D14
    L[3, 0] = d23 - D23
    L[4, 0] = d24 - D24
    L[5, 0] = d34 - D34

    while iter < 1000:
        P = T.dot(P)

        ATP = A.T.dot(P)
        ATPA = ATP.dot(A)
        ATPL = ATP.dot(L)

        try:
            ATPA1 = np.linalg.inv(ATPA)
        except np.linalg.LinAlgError:
            er = 2
            return OPe, 0, 0, 0, 0, 0, 0, 0, er
        else:
            dx = -ATPA1.dot(ATPL)

        Ad = A.dot(dx)
        V = Ad + L

        if iter > 0:
            stop_iter = True
            Vd = np.absolute(V - V1)
            if Vd.max() > eV:
                stop_iter = False

        V1 = V

        try:
            P1 = np.linalg.inv(P)
        except np.linalg.LinAlgError:
            er = 2
            break
        else:
            AATPA1 = A.dot(ATPA1)
            AATPA1AT = AATPA1.dot(A.T)
            Cv = P1 - AATPA1AT

        for i in range(6):
            Vv[i, 0] = V[i, 0] / np.sqrt(Cv[i, i])

        for i in range(6):
            if np.fabs(Vv.item(i, 0)) > k:
                T[i, i] = k / np.fabs(Vv.item(i, 0))
            else:
                T[i, i] = 1.0

        iter += 1
        if stop_iter:
            er = 0
            break

    OPe[0, 0] += dx[0, 0]
    OPe[1, 0] += dx[1, 0]

    VTP = V.T.dot(P)
    s = VTP.dot(V)
    mo2 = s.item(0) / (6 - 2.0)

    Cx = np.dot(mo2, ATPA1)
    M = np.sqrt(Cx[0, 0] + Cx[1, 1])
    Mx = np.sqrt(Cx[0, 0])
    My = np.sqrt(Cx[1, 1])

    DEL = ((ATPA[0, 0] - ATPA[1, 1]) * (ATPA[0, 0] - ATPA[1, 1])) + (4.0 * ATPA[0, 1] * ATPA[0, 1])
    li1 = (ATPA[0, 0] + ATPA[1, 1] - np.sqrt(DEL)) / 2.0
    li2 = (ATPA[0, 0] + ATPA[1, 1] + np.sqrt(DEL)) / 2.0
    fi_e = (np.rad2deg(np.arctan((2.0 * ATPA[0, 1] / (ATPA[0, 0] - ATPA[1, 1]))))) / 2.0

    f = 1.53553
    a_e = np.sqrt(mo2) * np.sqrt((2.0 * f) / li1)
    b_e = np.sqrt(mo2) * np.sqrt((2.0 * f) / li2)

    return OPe, mo2, M, Mx, My, fi_e, a_e, b_e, er


def position_estimation_TDOA_6(Po, H_list,
                               dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
                               B12, B13, B14, B23, B24, B34):
    H1, H2, H3, H4 = H_list

    OP_in = Po.copy()
    OP_in1 = OP_in.copy()

    OP_out_classic, mo2, M, Mx, My, fi_e, a_e, b_e, er_classic = Calculation_Position_2D_TDOA_6_Adjustment(
        OP_in, H1, H2, H3, H4,
        dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
        B12, B13, B14, B23, B24, B34
    )

    if er_classic != 2:
        OP_in1 = OP_out_classic.copy()

    OP_out_robust, mo2_r, M_r, Mx_r, My_r, fi_e_r, a_e_r, b_e_r, er_robust = Calculation_Position_2D_TDOA_6_Robust_Adjustment(
        OP_in1, H1, H2, H3, H4,
        dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
        B12, B13, B14, B23, B24, B34
    )

    # Corrected return tuple (your snippet missed a comma)
    return (
        OP_out_robust,
        M_r, Mx_r, My_r,
        a_e_r, b_e_r, fi_e_r,
        er_robust
    )
